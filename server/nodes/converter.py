"""
Converter node — converts the combined JSON block data into streamable layers.

Input:  combined_blocks (merged block list from combiner)
Output: build_layers (blocks grouped by Y-level for layer-by-layer streaming)
"""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def convert_to_layers(state: dict) -> dict:
    """Group combined blocks by Y-level for layer-by-layer streaming to the client."""
    # TODO: Group blocks by Y, create the layers dict for main.py to stream
    blocks = state.get("combined_blocks", [])
    logger.info(f"[converter] Converting {len(blocks)} blocks into streamable layers...")

    # Group by Y coordinate
    layers = defaultdict(list)
    for block in blocks:
        layers[block.get("y", 0)].append(block)

    sorted_y = sorted(layers.keys())
    build_layers = {}
    for i, y in enumerate(sorted_y):
        build_layers[i] = {
            "y_level": y,
            "blocks": layers[y],
        }

    return {
        "build_layers": build_layers,
        "total_layers": len(sorted_y),
    }
