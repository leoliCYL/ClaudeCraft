"""
Converter node — takes a build JSON (palette + components + placements),
runs block-state post-processing, and produces a .litematic file.

Input:  build_json  (the full JSON with palette, components, placements)
Output: schematic_path, schematic_name, build_layers, total_layers
"""

import os
import logging
import tempfile
from collections import defaultdict

from lib.litematica_writer import json_to_litematic
from lib.block_postprocessor import postprocess_blocks

logger = logging.getLogger(__name__)

_OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "claudecraft_builds")
os.makedirs(_OUTPUT_DIR, exist_ok=True)


def _resolve_to_flat(build_json: dict) -> tuple[dict, list[dict]]:
    """Resolve components + placements into a flat block list and palette."""
    palette = build_json.get("palette", {})
    palette_inv = {v: k for k, v in palette.items()}
    components = {c["name"]: c for c in build_json.get("components", [])}

    flat_blocks = []
    for placement in build_json.get("placements", []):
        comp = components.get(placement["component"])
        if not comp:
            continue
        ox = placement["position"]["x"]
        oy = placement["position"]["y"]
        oz = placement["position"]["z"]
        for z, z_slice in enumerate(comp["blocks"]):
            for y, y_row in enumerate(z_slice):
                for x, idx in enumerate(y_row):
                    if idx == 0:  # skip air
                        continue
                    flat_blocks.append({
                        "x": ox + x, "y": oy + y, "z": oz + z,
                        "block": palette_inv.get(idx, "minecraft:stone"),
                    })

    return palette, flat_blocks


def _flat_to_build_json(palette: dict, flat_blocks: list[dict]) -> dict:
    """Convert a flat block list back into the build JSON format."""
    if not flat_blocks:
        return {"palette": palette, "components": [], "placements": []}

    max_x = max(b["x"] for b in flat_blocks) + 1
    max_y = max(b["y"] for b in flat_blocks) + 1
    max_z = max(b["z"] for b in flat_blocks) + 1

    # Rebuild palette indices
    new_palette = {"minecraft:air": 0}
    for b in flat_blocks:
        if b["block"] not in new_palette:
            new_palette[b["block"]] = len(new_palette)

    blocks_3d = [[[0] * max_x for _ in range(max_y)] for _ in range(max_z)]
    for b in flat_blocks:
        blocks_3d[b["z"]][b["y"]][b["x"]] = new_palette[b["block"]]

    return {
        "palette": new_palette,
        "components": [{
            "name": "main",
            "size": {"x": max_x, "y": max_y, "z": max_z},
            "blocks": blocks_3d,
        }],
        "placements": [
            {"component": "main", "position": {"x": 0, "y": 0, "z": 0}}
        ],
    }


def convert_to_layers(state: dict) -> dict:
    """Convert build JSON into a .litematic file and streamable layers."""

    build_json = state.get("build_json")
    user_message = state.get("user_message", "build")

    if not build_json or not build_json.get("components"):
        logger.warning("[converter] No build_json or empty components — skipping")
        return {"build_layers": {}, "total_layers": 0}

    logger.info("[converter] Resolving placements...")

    # 1. Resolve to flat blocks
    palette, flat_blocks = _resolve_to_flat(build_json)

    # 2. Post-process block states (stairs, slabs, panes, etc.)
    palette, flat_blocks = postprocess_blocks(palette, flat_blocks)

    # 3. Rebuild JSON with updated palette (properties added)
    processed_json = _flat_to_build_json(palette, flat_blocks)

    # 4. Generate filename
    safe_name = "".join(c if c.isalnum() or c in " _-" else "" for c in user_message)[:40].strip()
    safe_name = safe_name.replace(" ", "_") or "build"
    output_path = os.path.join(_OUTPUT_DIR, f"{safe_name}.litematic")

    # 5. Write .litematic
    try:
        schematic_path = json_to_litematic(processed_json, output_path, name=safe_name)
    except Exception as e:
        logger.error(f"[converter] Failed to write litematic: {e}")
        return {"build_layers": {}, "total_layers": 0}

    # 6. Build streamable layers
    layers = defaultdict(list)
    for b in flat_blocks:
        layers[b["y"]].append(b)

    sorted_y = sorted(layers.keys())
    build_layers = {
        i: {"y_level": y, "blocks": layers[y]}
        for i, y in enumerate(sorted_y)
    }

    logger.info(f"\033[32m[converter] Saved {schematic_path} — {len(flat_blocks)} blocks, {len(sorted_y)} layers\033[0m")

    return {
        "schematic_path": schematic_path,
        "schematic_name": safe_name,
        "build_layers": build_layers,
        "total_layers": len(sorted_y),
    }
