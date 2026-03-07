"""
Component Builder node — builds a single component (runs in parallel for each component).

Input:  component spec, block_palette, reference_images
Output: component_blocks (list of placed blocks for this component)
"""

import logging

logger = logging.getLogger(__name__)


def build_component(state: dict) -> dict:
    """Build a single component — generates block placements for one part of the build."""
    # TODO: Use LLM to generate block-by-block placement for this component
    components = state.get("components", [])
    logger.info(f"[component_builder] Building {len(components)} components in parallel...")

    return {
        "component_results": [],  # list of built component block data
    }
