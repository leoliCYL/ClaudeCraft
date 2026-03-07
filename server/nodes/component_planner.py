"""
Component Planner node — breaks a build into components using palette + images.

Input:  user_message, reference_images, block_palette
Output: components (list of component specs to build in parallel)
"""

import logging

logger = logging.getLogger(__name__)


def plan_components(state: dict) -> dict:
    """Decompose the build into independent components that can be built in parallel."""
    # TODO: Use LLM to split the build into components (e.g. walls, roof, floor, furniture)
    logger.info(f"[component_planner] Planning components with {len(state.get('block_palette', []))} blocks...")

    return {
        "components": [],  # e.g. [{"name": "walls", "description": "...", "bounds": {...}}, ...]
    }
