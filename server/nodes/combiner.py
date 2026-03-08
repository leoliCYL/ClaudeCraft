"""
Combiner node — merges all component results into a single unified build JSON.

Input:  component_results (list of encoded components from parallel builders), palette_map
Output: build_json (dict with palette, components, placements ready for converter)
"""

import logging

logger = logging.getLogger(__name__)


def combine_components(state: dict) -> dict:
    """Merge all component block data into a single build_json for the converter."""
    results = state.get("component_results", [])
    palette_map = state.get("palette_map", {})

    logger.info(f"[combiner] Combining {len(results)} component results...")

    if not results:
        logger.warning("[combiner] No component results to combine.")
        return {"build_json": {}}

    # Invert palette_map: {idx: block_name} -> {block_name: idx}
    palette = {block_name: int(idx) for idx, block_name in palette_map.items()}

    # Stack components vertically — place each component on top of the previous
    placements = []
    current_y = 0

    for comp in results:
        name = comp.get("name", "unnamed")
        size_y = comp.get("size", {}).get("y", 0)

        placements.append({
            "component": name,
            "position": {"x": 0, "y": current_y, "z": 0},
        })

        current_y += size_y
        logger.info(f"  • Placed '{name}' at Y={current_y - size_y} (height={size_y})")

    build_json = {
        "palette": palette,
        "components": results,
        "placements": placements,
    }

    total_blocks = sum(
        comp.get("size", {}).get("x", 0) *
        comp.get("size", {}).get("y", 0) *
        comp.get("size", {}).get("z", 0)
        for comp in results
    )

    logger.info(
        f"\033[32m[combiner] Assembled build_json: {len(results)} components, "
        f"~{total_blocks} total volume, {len(palette)} palette entries\033[0m"
    )

    return {"build_json": build_json}
