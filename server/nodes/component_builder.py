"""
Component Builder node — builds a single component.
Each instance receives one component via Send() and runs in parallel.

Input:  current_component (single component spec from Send), block_palette, reference_images
Output: component_results (list with this component's block data — merged by LangGraph)
"""

import logging

logger = logging.getLogger(__name__)


def build_component(state: dict) -> dict:
    """Build a single component — generates block placements for one part of the build."""
    # TODO: Use LLM to generate block-by-block placement for this component
    comp = state.get("current_component")
    comp_name = comp.get("name", "unknown") if comp else "empty"
    logger.info(f"[component_builder] Building component: {comp_name}")

    return {
        "component_results": [],  # blocks for this component — merged across parallel runs
    }
