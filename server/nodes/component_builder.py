"""
Component Builder node — builds a single component.
Each instance receives one component via Send() and runs in parallel.

Input:  current_component (single component spec from planner), palette_map
Output: component_results (list with this component's encoded block data — merged by LangGraph)
"""

import random
import logging

logger = logging.getLogger(__name__)


def _invert_palette(palette_map: dict) -> dict:
    """Invert {idx: block_name} -> {block_name: idx}."""
    return {v: int(k) for k, v in palette_map.items()}


def _get_or_add(block_name: str, palette_map: dict, reverse: dict) -> int:
    """Get palette index, adding the block if it's missing."""
    if block_name in reverse:
        return reverse[block_name]
    next_id = max(int(k) for k in palette_map) + 1 if palette_map else 0
    palette_map[next_id] = block_name
    reverse[block_name] = next_id
    return next_id


import json
from langchain_core.messages import HumanMessage
from lib.llm_factory import get_llm
from prompts.system_prompts import component_builder_prompt


def _build_3d_grid(comp_name: str, desc: str, materials: list[str], x: int, y: int, z: int,
                    palette_map: dict, reverse: dict, reference_images: list) -> list:
    """
    Use an LLM to generate a [z][y][x] grid of palette IDs filled with the listed materials.
    """
    grid = [[[0 for _ in range(x)] for _ in range(y)] for _ in range(z)]
    if not materials:
        return grid

    prompt_text = component_builder_prompt(comp_name, desc, x, y, z, materials)

    content_parts = []
    for item in reference_images:
        data_url = item.get("data") if isinstance(item, dict) else item
        if data_url and data_url.startswith("data:"):
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": data_url},
            })

    content_parts.append({"type": "text", "text": prompt_text})

    llm = get_llm(temperature=0.4)
    logger.info(f"[component_builder] Asking LLM to build '{comp_name}' grid...")

    try:
        result = llm.invoke([HumanMessage(content=content_parts)])
        raw = result.content.strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            raw = raw.rsplit("```", 1)[0]

        parsed_grid = json.loads(raw)
        
        # Verify dimensions
        if len(parsed_grid) == z and len(parsed_grid[0]) == y and len(parsed_grid[0][0]) == x:
            # Map the local 1-N palette back to the global palette_map IDs
            for zi in range(z):
                for yi in range(y):
                    for xi in range(x):
                        local_idx = parsed_grid[zi][yi][xi]
                        if local_idx == 0:
                            grid[zi][yi][xi] = 0
                        elif 1 <= local_idx <= len(materials):
                            block_name = materials[local_idx - 1]
                            grid[zi][yi][xi] = _get_or_add(block_name, palette_map, reverse)
                        else:
                            grid[zi][yi][xi] = 0
            return grid
        else:
            logger.error(f"[component_builder] LLM returned wrong dimensions for '{comp_name}'. "
                         f"Expected {z}x{y}x{x}, got {len(parsed_grid)}x{len(parsed_grid[0])}x...")
    except Exception as e:
        logger.error(f"[component_builder] LLM generation failed for '{comp_name}': {e}")
        logger.debug(f"[component_builder] Raw LLM output: {raw[:500] if 'raw' in locals() else 'None'}")

    # Fallback to random placement if LLM fails
    logger.warning(f"[component_builder] Falling back to random placement for '{comp_name}'")
    for zi in range(z):
        for yi in range(y):
            for xi in range(x):
                block_name = random.choice(materials)
                grid[zi][yi][xi] = _get_or_add(block_name, palette_map, reverse)

    return grid


def build_component(state: dict) -> dict:
    """Build a single component — generates block placements for one part of the build."""
    comp = state.get("current_component")
    palette_map = dict(state.get("palette_map", {}))  # copy to avoid cross-mutation
    reference_images = state.get("reference_images", [])

    if not comp:
        logger.warning("[component_builder] No current_component found.")
        return {"component_results": []}

    comp_name = comp.get("component_name", "unknown")
    desc = comp.get("description", "")
    dims = comp.get("dimensions", {})
    x = int(dims.get("X", 1))
    y = int(dims.get("Y", 1))
    z = int(dims.get("Z", 1))
    materials = comp.get("blocks", [])

    logger.info(f"[component_builder] Building '{comp_name}' ({x}x{y}x{z}) with {len(materials)} block types")

    try:
        reverse = _invert_palette(palette_map)
        grid = _build_3d_grid(comp_name, desc, materials, x, y, z, palette_map, reverse, reference_images)

        encoded = {
            "name": comp_name.replace(" ", "_").lower(),
            "description": desc,
            "size": {"x": x, "y": y, "z": z},
            "blocks": grid,
        }

        logger.info(f"\033[32m[component_builder] Built '{comp_name}' → {x*y*z} blocks\033[0m")

        return {
            "component_results": [encoded],
            "palette_map": palette_map,
        }

    except Exception as e:
        logger.error(f"[component_builder] Failed to build '{comp_name}': {e}", exc_info=True)
        return {"component_results": []}