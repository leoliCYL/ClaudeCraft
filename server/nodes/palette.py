"""
Palette node — analyzes reference images to determine a Minecraft block palette.

Input:  reference_images (from image_search)
Output: block_palette (list of minecraft block IDs with usage hints)
"""

import logging

logger = logging.getLogger(__name__)


def extract_palette(state: dict) -> dict:
    """Analyze reference images and extract a block palette."""
    # TODO: Use vision LLM to analyze images and suggest Minecraft blocks
    logger.info(f"[palette] Extracting palette from {len(state.get('reference_images', []))} images...")

    return {
        "block_palette": [],  # e.g. [{"block": "minecraft:oak_planks", "use": "walls"}, ...]
    }
