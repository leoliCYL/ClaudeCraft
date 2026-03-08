"""
Component Builder node — builds a single component.
Each instance receives one component via Send() and runs in parallel.

Input:  current_component (single component spec from Send), block_palette, palette_map, reference_images
Output: component_results (list with this component's encoded block data — merged by LangGraph)
"""

import logging
import random

logger = logging.getLogger(__name__)


def invert_palette_map(palette_map: dict) -> dict:
    """
    Convert palette_map from:
        {0: "minecraft:air", 1: "minecraft:stone_bricks"}
    into:
        {"minecraft:air": 0, "minecraft:stone_bricks": 1}
    """
    reverse = {}
    for k, v in palette_map.items():
        reverse[v] = int(k) if isinstance(k, str) and str(k).isdigit() else k
    return reverse


def get_or_add_palette_id(block_name: str, palette_map: dict, reverse_palette: dict) -> int:
    """
    Uses existing palette if block exists.
    Adds block if missing.
    """
    if block_name in reverse_palette:
        return reverse_palette[block_name]

    next_id = max(int(k) for k in palette_map.keys()) + 1 if palette_map else 0
    palette_map[next_id] = block_name
    reverse_palette[block_name] = next_id
    return next_id


def build_3d_block_array(materials: list, x: int, y: int, z: int, palette_map: dict) -> list:
    """
    Creates a 3D array of palette IDs.
    For now this fills the component volume using the listed materials.
    Later you can replace this with real structural logic.
    """
    reverse_palette = invert_palette_map(palette_map)

    grid = [[[0 for _ in range(z)] for _ in range(y)] for _ in range(x)]

    if not materials:
        return grid

    for yi in range(y):
        for zi in range(z):
            for xi in range(x):
                block_name = random.choice(materials)
                block_id = get_or_add_palette_id(block_name, palette_map, reverse_palette)
                grid[xi][yi][zi] = block_id

    return grid


def encode_component(raw_component: dict, palette_map: dict) -> dict:
    """
    Converts raw Gemini schema into encoded component JSON.
    """
    name = raw_component.get("component_name", "unnamed_component")
    description = raw_component.get("description", "")
    dims = raw_component.get("dimensions", {})

    x = int(dims.get("X", 1))
    y = int(dims.get("Y", 1))
    z = int(dims.get("Z", 1))

    materials = raw_component.get("blocks", [])

    encoded_grid = build_3d_block_array(materials, x, y, z, palette_map)

    return {
        "name": name.replace(" ", "_").lower(),
        "description": description,
        "size": {
            "x": x,
            "y": y,
            "z": z
        },
        "blocks": encoded_grid
    }


def build_component(state: dict) -> dict:
    """Build a single component — generates block placements for one part of the build."""
    comp = state.get("current_component")
    palette_map = state.get("palette_map", {})

    if not comp:
        logger.warning("[component_builder] No current_component found.")
        return {"component_results": []}

    comp_name = comp.get("component_name", "unknown")
    logger.info(f"[component_builder] Building component: {comp_name}")

    try:
        encoded_component = encode_component(comp, palette_map)

        return {
            "component_results": [encoded_component],
            "palette_map": palette_map
        }

    except Exception as e:
        logger.error(f"[component_builder] Failed to build component {comp_name}: {e}", exc_info=True)
        return {
            "component_results": []
        }