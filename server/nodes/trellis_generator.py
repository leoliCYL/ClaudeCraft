"""
Trellis Generator node — calls Trellis via piapi.ai (image-to-3D),
voxelizes the resulting GLB, and applies the block palette.

Input:  reference_images, block_palette
Output: combined_blocks, build_json
"""

import os
import time
import logging
import tempfile

import httpx
import trimesh

from lib.voxelizer import voxelize_mesh

logger = logging.getLogger(__name__)

PIAPI_CREATE_URL = "https://api.piapi.ai/api/v1/task"
PIAPI_GET_URL    = "https://api.piapi.ai/api/v1/task/{task_id}"
POLL_INTERVAL    = 5   # seconds
MAX_POLLS        = 60  # 5 minutes max


def _pick_image(reference_images: list) -> str | None:
    for img in reference_images:
        if isinstance(img, str) and img.startswith("data:"):
            return img
        if isinstance(img, dict):
            data = img.get("data", "")
            if data.startswith("data:"):
                return data
    return None


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 3:
        hex_str = "".join([c*2 for c in hex_str])
    if len(hex_str) != 6:
        return (125, 125, 125)
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def _color_distance(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    return sum((a - b) ** 2 for a, b in zip(c1, c2, strict=False))

def _apply_palette(blocks: list[dict], palette: dict) -> list[dict]:
    """Assign Minecraft block IDs by finding the closest color in the palette."""
    if not blocks:
        return blocks
    
    palette_data = palette.get("palette", [{"block": "minecraft:stone_bricks", "hex": "#7D7D7D"}])
    
    parsed_palette = []
    for p in palette_data:
        b_id = p.get("block", "minecraft:stone")
        h = p.get("hex", "#7D7D7D")
        parsed_palette.append({
            "block": b_id,
            "rgb": _hex_to_rgb(h)
        })
        
    for b in blocks:
        block_color = tuple(b.get("color", [125, 125, 125]))
        
        best_block = parsed_palette[0]["block"]
        min_dist = float('inf')
        
        for p in parsed_palette:
            dist = _color_distance(block_color, p["rgb"])
            if dist < min_dist:
                min_dist = dist
                best_block = p["block"]
                
        b["block"] = best_block
        
    return blocks


def _blocks_to_build_json(blocks: list[dict]) -> dict:
    if not blocks:
        return {"palette": {"minecraft:air": 0}, "components": [], "placements": []}

    palette_map = {"minecraft:air": 0}
    for b in blocks:
        if b["block"] not in palette_map:
            palette_map[b["block"]] = len(palette_map)

    max_x = max(b["x"] for b in blocks) + 1
    max_y = max(b["y"] for b in blocks) + 1
    max_z = max(b["z"] for b in blocks) + 1

    blocks_3d = [[[0] * max_x for _ in range(max_y)] for _ in range(max_z)]
    for b in blocks:
        blocks_3d[b["z"]][b["y"]][b["x"]] = palette_map[b["block"]]

    return {
        "palette": palette_map,
        "components": [{
            "name": "main",
            "size": {"x": max_x, "y": max_y, "z": max_z},
            "blocks": blocks_3d,
        }],
        "placements": [{"component": "main", "position": {"x": 0, "y": 0, "z": 0}}],
    }


def generate_mesh(state: dict) -> dict:
    """Call Trellis (piapi.ai) to generate a 3D model, voxelize it, and apply the block palette."""
    reference_images = state.get("reference_images", [])
    block_palette = state.get("block_palette") or {}

    api_key = os.getenv("PIAPI_KEY")
    if not api_key:
        logger.error("[trellis_generator] PIAPI_KEY not set.")
        return {"combined_blocks": [], "build_json": None}

    image_data_url = _pick_image(reference_images)
    if not image_data_url:
        logger.error("[trellis_generator] No reference image available.")
        return {"combined_blocks": [], "build_json": None}

    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }

    # 1. Submit task
    try:
        payload = {
            "model": "Qubico/trellis",
            "task_type": "image-to-3d",
            "input": {
                "images": [image_data_url],
                "ss_sampling_steps": 12,
                "slat_sampling_steps": 12,
                "ss_guidance_strength": 7.5,
                "slat_guidance_strength": 3.0,
                "seed": 0,
            },
        }
        logger.info("\033[36m[trellis_generator] Submitting Trellis task to piapi.ai...\033[0m")
        resp = httpx.post(PIAPI_CREATE_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        task_id = data.get("data", {}).get("task_id")
        if not task_id:
            logger.error(f"[trellis_generator] No task_id in response: {data}")
            return {"combined_blocks": [], "build_json": None}
        logger.info(f"[trellis_generator] Task submitted. ID: {task_id}")
    except Exception as e:
        logger.error(f"[trellis_generator] Failed to submit task: {e}", exc_info=True)
        return {"combined_blocks": [], "build_json": None}

    # 2. Poll for completion
    glb_url = None
    for attempt in range(MAX_POLLS):
        time.sleep(POLL_INTERVAL)
        try:
            poll_resp = httpx.get(
                PIAPI_GET_URL.format(task_id=task_id),
                headers=headers,
                timeout=15,
            )
            poll_resp.raise_for_status()
            poll_data = poll_resp.json().get("data", {})
            status = poll_data.get("status", "")
            logger.info(f"[trellis_generator] Status ({attempt+1}/{MAX_POLLS}): {status}")

            if status.lower() == "completed":
                glb_url = poll_data.get("output", {}).get("model_file")
                break
            elif status.lower() == "failed":
                logger.error(f"[trellis_generator] Task failed: {poll_data}")
                return {"combined_blocks": [], "build_json": None}
        except Exception as e:
            logger.warning(f"[trellis_generator] Polling error: {e}")

    if not glb_url:
        logger.error("[trellis_generator] Timed out waiting for Trellis result.")
        return {"combined_blocks": [], "build_json": None}

    # 3. Download GLB
    try:
        logger.info(f"[trellis_generator] Downloading GLB from {glb_url[:60]}...")
        glb_resp = httpx.get(glb_url, timeout=60, follow_redirects=True)
        glb_resp.raise_for_status()

        temp_glb = tempfile.NamedTemporaryFile(delete=False, suffix=".glb")
        temp_glb.write(glb_resp.content)
        temp_glb.close()
        logger.info(f"[trellis_generator] GLB saved ({len(glb_resp.content)//1024} KB)")
    except Exception as e:
        logger.error(f"[trellis_generator] Failed to download GLB: {e}")
        return {"combined_blocks": [], "build_json": None}

    # 4. Convert GLB → OBJ for voxelizer
    try:
        scene = trimesh.load(temp_glb.name, force="mesh")
        if isinstance(scene, trimesh.Scene):
            mesh = trimesh.util.concatenate(list(scene.geometry.values()))
        else:
            mesh = scene

        temp_obj = tempfile.NamedTemporaryFile(delete=False, suffix=".obj")
        temp_obj.close()
        mesh.export(temp_obj.name)
    except Exception as e:
        logger.error(f"[trellis_generator] Mesh conversion failed: {e}")
        return {"combined_blocks": [], "build_json": None}

    # 5. Voxelize
    max_size = int(os.getenv("MAX_VOXEL_SIZE", 100))
    blocks = voxelize_mesh(temp_obj.name, max_size=max_size)

    if not blocks:
        logger.error("[trellis_generator] Voxelization produced no blocks.")
        return {"combined_blocks": [], "build_json": None}

    # 6. Apply block palette (independent of mesh colors)
    blocks = _apply_palette(blocks, block_palette)
    build_json = _blocks_to_build_json(blocks)

    logger.info(f"\033[32m[trellis_generator] Done — {len(blocks)} blocks, palette length: {len(block_palette.get('palette', []))}\033[0m")
    logger.info(f"\033[36m[trellis_generator] 3D Files available at:\n  GLB: {temp_glb.name}\n  OBJ: {temp_obj.name}\033[0m")
    return {"combined_blocks": blocks, "build_json": build_json, "glb_path": temp_glb.name, "obj_path": temp_obj.name}
