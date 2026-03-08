"""
Schematic Parser — reads .litematic files and extracts blocks grouped by Y-layer.

Litematica format:
  - Regions → each region has Size, Position, BlockStatePalette, BlockStates
  - BlockStates are bit-packed into a long array
  - Sizes can be negative (region extends in negative direction)
  - Block ordering: for y in range(sizeY): for z in range(sizeZ): for x in range(sizeX)
"""

import math
import logging
from collections import defaultdict
from pathlib import Path

import nbtlib

logger = logging.getLogger(__name__)


def _unpack_blockstates(long_array: list[int], bits_per_entry: int, total_blocks: int) -> list[int]:
    """Unpack bit-packed block state indices from a long array."""
    indices = []
    mask = (1 << bits_per_entry) - 1

    for i in range(total_blocks):
        bit_index = i * bits_per_entry
        long_index = bit_index // 64
        bit_offset = bit_index % 64

        if long_index >= len(long_array):
            break

        # Get the value from the current long (handle as unsigned)
        value = (long_array[long_index] >> bit_offset) & mask

        # If the value spans two longs, grab the remaining bits
        if bit_offset + bits_per_entry > 64 and long_index + 1 < len(long_array):
            remaining_bits = bit_offset + bits_per_entry - 64
            value |= (long_array[long_index + 1] & ((1 << remaining_bits) - 1)) << (64 - bit_offset)

        indices.append(value)

    return indices


def parse_litematic(file_path: str) -> dict:
    """
    Parse a .litematic file and return blocks grouped by Y-layer.

    Returns:
        {
            "name": str,
            "total_layers": int,
            "layers": {
                0: [{"x": int, "y": int, "z": int, "block": "minecraft:stone"}, ...],
                1: [...],
                ...
            }
        }
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Schematic file not found: {file_path}")

    nbt_file = nbtlib.load(str(path))

    # Extract metadata
    metadata = nbt_file.get("Metadata", {})
    name = str(metadata.get("Name", path.stem))

    regions = nbt_file.get("Regions", {})
    if not regions:
        raise ValueError(f"No regions found in schematic: {file_path}")

    # Collect all blocks across all regions, grouped by Y
    layers: dict[int, list[dict]] = defaultdict(list)

    for region_name, region in regions.items():
        # Get region dimensions (can be negative)
        size = region["Size"]
        sx, sy, sz = int(size["x"]), int(size["y"]), int(size["z"])

        # Get region position offset
        pos = region["Position"]
        px, py, pz = int(pos["x"]), int(pos["y"]), int(pos["z"])

        # Absolute sizes for iteration
        abs_sx, abs_sy, abs_sz = abs(sx), abs(sy), abs(sz)
        total_blocks = abs_sx * abs_sy * abs_sz

        # Build palette: index -> block name
        palette = region["BlockStatePalette"]
        palette_map = {}
        for i, entry in enumerate(palette):
            block_name = str(entry["Name"])
            # Include properties if present
            if "Properties" in entry:
                props = entry["Properties"]
                prop_str = ",".join(f"{k}={v}" for k, v in props.items())
                block_name += f"[{prop_str}]"
            palette_map[i] = block_name

        # Calculate bits per entry
        palette_size = len(palette)
        bits_per_entry = max(2, math.ceil(math.log2(palette_size))) if palette_size > 1 else 2

        # Unpack block state indices
        block_states_raw = region["BlockStates"]
        long_array = [int(v) for v in block_states_raw]
        indices = _unpack_blockstates(long_array, bits_per_entry, total_blocks)

        logger.info(
            f"Region '{region_name}': size=({abs_sx},{abs_sy},{abs_sz}), "
            f"palette={palette_size}, bits={bits_per_entry}, blocks={len(indices)}"
        )

        # Map indices to blocks with positions
        # Litematica block order: for y, for z, for x
        idx = 0
        for y in range(abs_sy):
            for z in range(abs_sz):
                for x in range(abs_sx):
                    if idx >= len(indices):
                        break

                    block_index = indices[idx]
                    idx += 1

                    if block_index >= len(palette_map):
                        continue

                    block_name = palette_map[block_index]

                    # Skip air blocks
                    if block_name == "minecraft:air":
                        continue

                    # Calculate world-relative position
                    # If size is negative, blocks go in negative direction
                    wx = px + (x if sx > 0 else -x)
                    wy = py + (y if sy > 0 else -y)
                    wz = pz + (z if sz > 0 else -z)

                    layers[wy].append({
                        "x": wx,
                        "y": wy,
                        "z": wz,
                        "block": block_name,
                    })

    # Sort by Y level
    sorted_y_levels = sorted(layers.keys())
    total_layers = len(sorted_y_levels)

    # Re-index layers from 0
    ordered_layers = {}
    for i, y_level in enumerate(sorted_y_levels):
        ordered_layers[i] = {
            "y_level": y_level,
            "blocks": layers[y_level],
        }

    total_blocks_placed = sum(len(l["blocks"]) for l in ordered_layers.values())
    logger.info(f"Parsed schematic '{name}': {total_layers} layers, {total_blocks_placed} non-air blocks")

    return {
        "name": name,
        "total_layers": total_layers,
        "layers": ordered_layers,
    }


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import json

    logging.basicConfig(level=logging.INFO)

    path = sys.argv[1] if len(sys.argv) > 1 else "assets/smallTest.litematic"
    result = parse_litematic(path)

    print(f"\nSchematic: {result['name']}")
    print(f"Total layers: {result['total_layers']}")
    for i, layer_data in result["layers"].items():
        print(f"  Layer {i} (Y={layer_data['y_level']}): {len(layer_data['blocks'])} blocks")
