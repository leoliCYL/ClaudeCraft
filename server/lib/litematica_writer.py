"""
Litematica Writer — converts JSON build data into a .litematic file.

Expected JSON input format:
{
  "palette": { "minecraft:air": 0, "minecraft:cobblestone": 1, ... },
  "components": [
    {
      "name": "tower",
      "size": { "x": 3, "y": 2, "z": 3 },
      "blocks": [[[1,1,1],[1,2,1]], ...]   # [z][y][x] indexed by palette int
    }
  ],
  "placements": [
    { "component": "tower", "position": { "x": 0, "y": 0, "z": 0 } }
  ]
}

The .litematic format uses NBT with:
  - Metadata (name, author, size, etc.)
  - Regions → each with Size, Position, BlockStatePalette, bit-packed BlockStates
  - Block ordering: for y in range(sizeY): for z in range(sizeZ): for x in range(sizeX)
"""

import math
import time
import logging
from collections import defaultdict
from pathlib import Path

import nbtlib
from nbtlib import (
    Compound, List, String, Int, Long, Short, Byte,
)

logger = logging.getLogger(__name__)


def _pack_blockstates(indices: list[int], bits_per_entry: int) -> list[int]:
    """Pack block state indices into a bit-packed long array (reverse of _unpack_blockstates)."""
    if bits_per_entry < 2:
        bits_per_entry = 2

    total_bits = len(indices) * bits_per_entry
    num_longs = math.ceil(total_bits / 64)
    longs = [0] * num_longs
    mask_64 = (1 << 64) - 1  # 0xFFFFFFFFFFFFFFFF

    for i, index in enumerate(indices):
        bit_index = i * bits_per_entry
        long_index = bit_index // 64
        bit_offset = bit_index % 64

        longs[long_index] = (longs[long_index] | ((index & ((1 << bits_per_entry) - 1)) << bit_offset)) & mask_64

        # Handle spanning across two longs
        if bit_offset + bits_per_entry > 64 and long_index + 1 < num_longs:
            remaining_bits = bit_offset + bits_per_entry - 64
            longs[long_index + 1] = (longs[long_index + 1] | ((index >> (bits_per_entry - remaining_bits)) & ((1 << remaining_bits) - 1))) & mask_64

    # Convert unsigned 64-bit to signed 64-bit (Java longs)
    import ctypes
    signed_longs = [ctypes.c_int64(v).value for v in longs]

    return signed_longs


def _resolve_placements(build_json: dict) -> tuple[dict[str, int], list[dict], tuple[int, int, int]]:
    """
    Resolve component placements into a flat block grid.
    
    Returns:
        - palette_map: { "minecraft:stone": 0, ... }
        - blocks: [{"x": int, "y": int, "z": int, "palette_idx": int}, ...]
        - total_size: (size_x, size_y, size_z)
    """
    palette = build_json.get("palette", {})
    components = {c["name"]: c for c in build_json.get("components", [])}
    placements = build_json.get("placements", [])

    all_blocks = []
    max_x, max_y, max_z = 0, 0, 0

    for placement in placements:
        comp_name = placement["component"]
        comp = components.get(comp_name)
        if not comp:
            logger.warning(f"[litematica_writer] Component '{comp_name}' not found, skipping")
            continue

        ox = placement["position"]["x"]
        oy = placement["position"]["y"]
        oz = placement["position"]["z"]

        comp_blocks = comp["blocks"]  # [z][y][x]
        size_z = len(comp_blocks)
        size_y = len(comp_blocks[0]) if size_z > 0 else 0
        size_x = len(comp_blocks[0][0]) if size_y > 0 else 0

        for z in range(size_z):
            for y in range(size_y):
                for x in range(size_x):
                    palette_idx = comp_blocks[z][y][x]
                    if palette_idx == 0:  # skip air (index 0)
                        continue
                    wx, wy, wz = ox + x, oy + y, oz + z
                    all_blocks.append({"x": wx, "y": wy, "z": wz, "palette_idx": palette_idx})
                    max_x = max(max_x, wx + 1)
                    max_y = max(max_y, wy + 1)
                    max_z = max(max_z, wz + 1)

    return palette, all_blocks, (max_x, max_y, max_z)


def json_to_litematic(build_json: dict, output_path: str, name: str = "ClaudeCraft Build") -> str:
    """
    Convert a JSON build definition into a .litematic file.

    Args:
        build_json: The build data with palette, components, and placements
        output_path: Where to save the .litematic file
        name: Display name for the schematic

    Returns:
        The output file path
    """
    palette_map, blocks, (size_x, size_y, size_z) = _resolve_placements(build_json)

    if not blocks:
        logger.warning("[litematica_writer] No blocks to write!")

    # Ensure minimum size of 1
    size_x = max(size_x, 1)
    size_y = max(size_y, 1)
    size_z = max(size_z, 1)

    logger.info(f"[litematica_writer] Building {size_x}x{size_y}x{size_z} schematic with {len(blocks)} blocks")

    # --- Build the BlockStatePalette ---
    # Invert palette: idx -> block_name
    idx_to_block = {v: k for k, v in palette_map.items()}
    # Ensure air is at index 0
    if 0 not in idx_to_block:
        idx_to_block[0] = "minecraft:air"

    palette_size = max(idx_to_block.keys()) + 1
    nbt_palette = List[Compound]()
    for i in range(palette_size):
        block_name = idx_to_block.get(i, "minecraft:air")
        # Handle block properties like minecraft:oak_stairs[facing=north]
        if "[" in block_name:
            base_name, props_str = block_name.split("[", 1)
            props_str = props_str.rstrip("]")
            properties = Compound()
            for prop in props_str.split(","):
                k, v = prop.split("=", 1)
                properties[k.strip()] = String(v.strip())
            nbt_palette.append(Compound({"Name": String(base_name), "Properties": properties}))
        else:
            nbt_palette.append(Compound({"Name": String(block_name)}))

    # --- Build the BlockStates bit-packed array ---
    # Create a 3D grid initialized to air (0)
    total_blocks = size_x * size_y * size_z
    grid = [0] * total_blocks

    # Place blocks into the grid
    # Litematica order: for y, for z, for x
    for block in blocks:
        x, y, z = block["x"], block["y"], block["z"]
        if 0 <= x < size_x and 0 <= y < size_y and 0 <= z < size_z:
            idx = y * (size_z * size_x) + z * size_x + x
            grid[idx] = block["palette_idx"]

    bits_per_entry = max(2, math.ceil(math.log2(palette_size))) if palette_size > 1 else 2
    packed_states = _pack_blockstates(grid, bits_per_entry)

    logger.info(f"[litematica_writer] Palette: {palette_size} entries, {bits_per_entry} bits/entry, {len(packed_states)} longs")

    # --- Build the NBT structure ---

    region = Compound({
        "Position": Compound({
            "x": Int(0),
            "y": Int(0),
            "z": Int(0),
        }),
        "Size": Compound({
            "x": Int(size_x),
            "y": Int(size_y),
            "z": Int(size_z),
        }),
        "BlockStatePalette": nbt_palette,
        "BlockStates": nbtlib.LongArray(packed_states),
        "Entities": List[Compound](),
        "TileEntities": List[Compound](),
        "PendingBlockTicks": List[Compound](),
        "PendingFluidTicks": List[Compound](),
    })

    root = Compound({
        "MinecraftDataVersion": Int(3953),  # 1.21.1
        "Version": Int(6),  # Litematica format version
        "SubVersion": Int(1),
        "Metadata": Compound({
            "Name": String(name),
            "Author": String("ClaudeCraft"),
            "Description": String("Generated by ClaudeCraft AI"),
            "TimeCreated": Long(int(time.time() * 1000)),
            "TimeModified": Long(int(time.time() * 1000)),
            "RegionCount": Int(1),
            "TotalBlocks": Int(len(blocks)),
            "TotalVolume": Int(total_blocks),
            "EnclosingSize": Compound({
                "x": Int(size_x),
                "y": Int(size_y),
                "z": Int(size_z),
            }),
        }),
        "Regions": Compound({
            "Main": region,
        }),
    })

    # Save as gzipped NBT
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    nbt_file = nbtlib.File(root, gzipped=True)
    nbt_file.save(str(out))

    logger.info(f"\033[32m[litematica_writer] Saved schematic to {out}\033[0m")
    return str(out)


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import json as json_mod

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        # Use the example from the user
        test_json = {
            "palette": {
                "minecraft:air": 0,
                "minecraft:cobblestone": 1,
                "minecraft:glass_pane": 2,
                "minecraft:oak_stairs": 3,
                "minecraft:oak_log": 4,
            },
            "components": [
                {
                    "name": "tower",
                    "size": {"x": 3, "y": 2, "z": 3},
                    "blocks": [
                        [[1, 1, 1], [1, 2, 1]],
                        [[1, 1, 1], [1, 2, 1]],
                        [[1, 1, 1], [1, 1, 1]],
                    ],
                },
                {
                    "name": "roof",
                    "size": {"x": 3, "y": 1, "z": 3},
                    "blocks": [
                        [[3, 3, 3]],
                        [[3, 4, 3]],
                        [[3, 3, 3]],
                    ],
                },
            ],
            "placements": [
                {"component": "tower", "position": {"x": 0, "y": 0, "z": 0}},
                {"component": "roof", "position": {"x": 0, "y": 2, "z": 0}},
            ],
        }
    else:
        with open(sys.argv[1]) as f:
            test_json = json_mod.load(f)

    out_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/test_output.litematic"
    json_to_litematic(test_json, out_path, name="Test Build")
    print(f"Written to {out_path}")

    # Verify by parsing it back
    from schematic_parser import parse_litematic
    result = parse_litematic(out_path)
    print(f"Verified: {result['total_layers']} layers, "
          f"{sum(len(l['blocks']) for l in result['layers'].values())} blocks")
