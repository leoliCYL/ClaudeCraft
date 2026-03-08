"""
Block State Post-Processor — auto-infers block properties based on neighbors.

Handles:
  - Stairs:      facing, half, shape
  - Slabs:       type (top/bottom)
  - Glass panes: north/south/east/west connections
  - Fences:      north/south/east/west connections
  - Walls:       north/south/east/west connections
  - Doors:       half, facing, hinge
  - Logs:        axis
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Block categories for fast lookups
_STAIR_BLOCKS = {
    "minecraft:oak_stairs", "minecraft:spruce_stairs", "minecraft:birch_stairs",
    "minecraft:jungle_stairs", "minecraft:acacia_stairs", "minecraft:dark_oak_stairs",
    "minecraft:mangrove_stairs", "minecraft:cherry_stairs", "minecraft:bamboo_stairs",
    "minecraft:stone_stairs", "minecraft:cobblestone_stairs", "minecraft:stone_brick_stairs",
    "minecraft:mossy_stone_brick_stairs", "minecraft:granite_stairs", "minecraft:polished_granite_stairs",
    "minecraft:diorite_stairs", "minecraft:polished_diorite_stairs", "minecraft:andesite_stairs",
    "minecraft:polished_andesite_stairs", "minecraft:deepslate_brick_stairs", "minecraft:deepslate_tile_stairs",
    "minecraft:cobbled_deepslate_stairs", "minecraft:polished_deepslate_stairs",
    "minecraft:sandstone_stairs", "minecraft:smooth_sandstone_stairs", "minecraft:red_sandstone_stairs",
    "minecraft:smooth_red_sandstone_stairs", "minecraft:brick_stairs", "minecraft:mud_brick_stairs",
    "minecraft:nether_brick_stairs", "minecraft:quartz_stairs", "minecraft:smooth_quartz_stairs",
    "minecraft:prismarine_stairs", "minecraft:prismarine_brick_stairs",
    "minecraft:tuff_stairs", "minecraft:polished_tuff_stairs", "minecraft:tuff_brick_stairs",
}

_SLAB_BLOCKS = {
    "minecraft:oak_slab", "minecraft:spruce_slab", "minecraft:birch_slab",
    "minecraft:jungle_slab", "minecraft:acacia_slab", "minecraft:dark_oak_slab",
    "minecraft:mangrove_slab", "minecraft:cherry_slab", "minecraft:bamboo_slab",
    "minecraft:stone_slab", "minecraft:cobblestone_slab", "minecraft:stone_brick_slab",
    "minecraft:mossy_stone_brick_slab", "minecraft:granite_slab", "minecraft:polished_granite_slab",
    "minecraft:diorite_slab", "minecraft:polished_diorite_slab", "minecraft:andesite_slab",
    "minecraft:polished_andesite_slab", "minecraft:deepslate_brick_slab", "minecraft:deepslate_tile_slab",
    "minecraft:sandstone_slab", "minecraft:smooth_sandstone_slab", "minecraft:red_sandstone_slab",
    "minecraft:brick_slab", "minecraft:mud_brick_slab", "minecraft:nether_brick_slab",
    "minecraft:quartz_slab", "minecraft:smooth_quartz_slab", "minecraft:prismarine_slab",
    "minecraft:prismarine_brick_slab", "minecraft:tuff_slab", "minecraft:polished_tuff_slab",
}

_PANE_BLOCKS = {
    "minecraft:glass_pane", "minecraft:iron_bars",
    "minecraft:white_stained_glass_pane", "minecraft:light_gray_stained_glass_pane",
    "minecraft:gray_stained_glass_pane", "minecraft:black_stained_glass_pane",
    "minecraft:brown_stained_glass_pane", "minecraft:red_stained_glass_pane",
    "minecraft:orange_stained_glass_pane", "minecraft:yellow_stained_glass_pane",
    "minecraft:lime_stained_glass_pane", "minecraft:green_stained_glass_pane",
    "minecraft:cyan_stained_glass_pane", "minecraft:light_blue_stained_glass_pane",
    "minecraft:blue_stained_glass_pane", "minecraft:purple_stained_glass_pane",
    "minecraft:magenta_stained_glass_pane", "minecraft:pink_stained_glass_pane",
}

_FENCE_BLOCKS = {
    "minecraft:oak_fence", "minecraft:spruce_fence", "minecraft:birch_fence",
    "minecraft:jungle_fence", "minecraft:acacia_fence", "minecraft:dark_oak_fence",
    "minecraft:mangrove_fence", "minecraft:cherry_fence", "minecraft:bamboo_fence",
    "minecraft:nether_brick_fence", "minecraft:crimson_fence", "minecraft:warped_fence",
}

_WALL_BLOCKS = {
    "minecraft:cobblestone_wall", "minecraft:mossy_cobblestone_wall",
    "minecraft:stone_brick_wall", "minecraft:mossy_stone_brick_wall",
    "minecraft:granite_wall", "minecraft:diorite_wall", "minecraft:andesite_wall",
    "minecraft:brick_wall", "minecraft:sandstone_wall", "minecraft:red_sandstone_wall",
    "minecraft:nether_brick_wall", "minecraft:deepslate_brick_wall",
    "minecraft:cobbled_deepslate_wall", "minecraft:polished_deepslate_wall",
    "minecraft:tuff_wall", "minecraft:polished_tuff_wall", "minecraft:tuff_brick_wall",
}

_DOOR_BLOCKS = {
    "minecraft:oak_door", "minecraft:spruce_door", "minecraft:birch_door",
    "minecraft:jungle_door", "minecraft:acacia_door", "minecraft:dark_oak_door",
    "minecraft:mangrove_door", "minecraft:cherry_door", "minecraft:bamboo_door",
    "minecraft:iron_door", "minecraft:copper_door",
}

_LOG_BLOCKS = {
    "minecraft:oak_log", "minecraft:spruce_log", "minecraft:birch_log",
    "minecraft:jungle_log", "minecraft:acacia_log", "minecraft:dark_oak_log",
    "minecraft:mangrove_log", "minecraft:cherry_log", "minecraft:pale_oak_log",
    "minecraft:oak_wood", "minecraft:spruce_wood", "minecraft:birch_wood",
}

# Connectables: blocks that panes/fences/walls will connect to
_CONNECTABLE = (_PANE_BLOCKS | _FENCE_BLOCKS | _WALL_BLOCKS)


def _strip_props(block_id: str) -> str:
    """Strip [properties] from a block ID → base name."""
    return block_id.split("[")[0] if "[" in block_id else block_id


def _is_solid(base: str) -> bool:
    """Rough check if a block is solid (panes/fences connect to solid blocks)."""
    if base == "minecraft:air":
        return False
    # Non-solid blocks
    non_solid = {"minecraft:water", "minecraft:lava", "minecraft:cobweb",
                 "minecraft:flower_pot", "minecraft:campfire", "minecraft:chain",
                 "minecraft:lantern", "minecraft:soul_lantern"}
    if base in non_solid:
        return False
    if base in _PANE_BLOCKS or base in _FENCE_BLOCKS or base in _DOOR_BLOCKS:
        return False
    if base in _SLAB_BLOCKS or base in _STAIR_BLOCKS:
        return True
    return True


def postprocess_blocks(palette: dict, flat_blocks: list[dict]) -> tuple[dict, list[dict]]:
    """
    Auto-infer block properties based on neighbors.
    
    Args:
        palette: {"minecraft:stone": 1, ...} — block name → palette index
        flat_blocks: [{"x": 0, "y": 0, "z": 0, "block": "minecraft:oak_stairs"}, ...]
    
    Returns:
        Updated (palette, flat_blocks) with properties added to block names.
    """
    if not flat_blocks:
        return palette, flat_blocks

    # Build spatial lookup: (x,y,z) -> base block name
    grid: dict[tuple[int, int, int], str] = {}
    for b in flat_blocks:
        grid[(b["x"], b["y"], b["z"])] = _strip_props(b["block"])

    def neighbor(x, y, z, dx, dy, dz) -> Optional[str]:
        return grid.get((x + dx, y + dy, z + dz))

    new_palette = dict(palette)  # will grow as we add property variants
    processed = []
    stair_data: dict[tuple[int, int, int], dict] = {}  # pass 1 stair info
    stats = {"stairs": 0, "slabs": 0, "panes": 0, "fences": 0, "walls": 0, "doors": 0, "logs": 0}

    for b in flat_blocks:
        x, y, z = b["x"], b["y"], b["z"]
        base = _strip_props(b["block"])
        new_block = base  # default: unchanged

        # ── Stairs (pass 1: facing + half only, shape in pass 2) ──
        if base in _STAIR_BLOCKS:
            n = neighbor(x, y, z, 0, 0, -1)  # north
            s = neighbor(x, y, z, 0, 0, 1)   # south
            e = neighbor(x, y, z, 1, 0, 0)   # east
            w = neighbor(x, y, z, -1, 0, 0)  # west

            n_solid = n and _is_solid(n)
            s_solid = s and _is_solid(s)
            e_solid = e and _is_solid(e)
            w_solid = w and _is_solid(w)

            # Face toward the solid neighbor (back of stair against wall)
            if n_solid and not s_solid:
                facing = "north"
            elif s_solid and not n_solid:
                facing = "south"
            elif e_solid and not w_solid:
                facing = "east"
            elif w_solid and not e_solid:
                facing = "west"
            else:
                facing = "north"  # default

            above = neighbor(x, y, z, 0, 1, 0)
            below = neighbor(x, y, z, 0, -1, 0)
            if above and _is_solid(above) and not (below and _is_solid(below)):
                half = "top"
            else:
                half = "bottom"

            # Store facing/half for pass 2, shape is placeholder
            stair_data[(x, y, z)] = {"facing": facing, "half": half, "base": base}
            new_block = base  # will be finalized in pass 2
            stats["stairs"] += 1

        # ── Slabs ──
        elif base in _SLAB_BLOCKS:
            above = neighbor(x, y, z, 0, 1, 0)
            below = neighbor(x, y, z, 0, -1, 0)
            if above and _is_solid(above) and not (below and _is_solid(below)):
                slab_type = "top"
            else:
                slab_type = "bottom"
            new_block = f"{base}[type={slab_type}]"
            stats["slabs"] += 1

        # ── Glass Panes / Iron Bars ──
        elif base in _PANE_BLOCKS:
            n = neighbor(x, y, z, 0, 0, -1)
            s = neighbor(x, y, z, 0, 0, 1)
            e = neighbor(x, y, z, 1, 0, 0)
            w = neighbor(x, y, z, -1, 0, 0)
            props = {
                "north": "true" if (n and (_is_solid(n) or n in _PANE_BLOCKS)) else "false",
                "south": "true" if (s and (_is_solid(s) or s in _PANE_BLOCKS)) else "false",
                "east":  "true" if (e and (_is_solid(e) or e in _PANE_BLOCKS)) else "false",
                "west":  "true" if (w and (_is_solid(w) or w in _PANE_BLOCKS)) else "false",
            }
            prop_str = ",".join(f"{k}={v}" for k, v in sorted(props.items()))
            new_block = f"{base}[{prop_str}]"
            stats["panes"] += 1

        # ── Fences ──
        elif base in _FENCE_BLOCKS:
            n = neighbor(x, y, z, 0, 0, -1)
            s = neighbor(x, y, z, 0, 0, 1)
            e = neighbor(x, y, z, 1, 0, 0)
            w = neighbor(x, y, z, -1, 0, 0)
            props = {
                "north": "true" if (n and (_is_solid(n) or n in _FENCE_BLOCKS)) else "false",
                "south": "true" if (s and (_is_solid(s) or s in _FENCE_BLOCKS)) else "false",
                "east":  "true" if (e and (_is_solid(e) or e in _FENCE_BLOCKS)) else "false",
                "west":  "true" if (w and (_is_solid(w) or w in _FENCE_BLOCKS)) else "false",
            }
            prop_str = ",".join(f"{k}={v}" for k, v in sorted(props.items()))
            new_block = f"{base}[{prop_str}]"
            stats["fences"] += 1

        # ── Walls ──
        elif base in _WALL_BLOCKS:
            n = neighbor(x, y, z, 0, 0, -1)
            s = neighbor(x, y, z, 0, 0, 1)
            e = neighbor(x, y, z, 1, 0, 0)
            w = neighbor(x, y, z, -1, 0, 0)
            up = neighbor(x, y, z, 0, 1, 0)
            props = {
                "north": "low" if (n and (_is_solid(n) or n in _WALL_BLOCKS)) else "none",
                "south": "low" if (s and (_is_solid(s) or s in _WALL_BLOCKS)) else "none",
                "east":  "low" if (e and (_is_solid(e) or e in _WALL_BLOCKS)) else "none",
                "west":  "low" if (w and (_is_solid(w) or w in _WALL_BLOCKS)) else "none",
                "up":    "true" if (up and _is_solid(up)) else "false",
            }
            prop_str = ",".join(f"{k}={v}" for k, v in sorted(props.items()))
            new_block = f"{base}[{prop_str}]"
            stats["walls"] += 1

        # ── Doors ──
        elif base in _DOOR_BLOCKS:
            above = neighbor(x, y, z, 0, 1, 0)
            below = neighbor(x, y, z, 0, -1, 0)

            if below and _strip_props(below) == base:
                door_half = "upper"
            else:
                door_half = "lower"

            # Face towards open space
            n_solid = neighbor(x, y, z, 0, 0, -1) and _is_solid(neighbor(x, y, z, 0, 0, -1))
            s_solid = neighbor(x, y, z, 0, 0, 1) and _is_solid(neighbor(x, y, z, 0, 0, 1))
            e_solid = neighbor(x, y, z, 1, 0, 0) and _is_solid(neighbor(x, y, z, 1, 0, 0))
            w_solid = neighbor(x, y, z, -1, 0, 0) and _is_solid(neighbor(x, y, z, -1, 0, 0))

            if not n_solid:
                facing = "north"
            elif not s_solid:
                facing = "south"
            elif not e_solid:
                facing = "east"
            else:
                facing = "west"

            new_block = f"{base}[facing={facing},half={door_half},hinge=left,open=false]"
            stats["doors"] += 1

        # ── Logs ──
        elif base in _LOG_BLOCKS:
            # Determine axis based on which direction the log extends
            above = neighbor(x, y, z, 0, 1, 0)
            below = neighbor(x, y, z, 0, -1, 0)
            n = neighbor(x, y, z, 0, 0, -1)
            s = neighbor(x, y, z, 0, 0, 1)
            e = neighbor(x, y, z, 1, 0, 0)
            w = neighbor(x, y, z, -1, 0, 0)

            same_above = above == base
            same_below = below == base
            same_ns = (n == base) or (s == base)
            same_ew = (e == base) or (w == base)

            if same_ns and not same_ew and not (same_above or same_below):
                axis = "z"
            elif same_ew and not same_ns and not (same_above or same_below):
                axis = "x"
            else:
                axis = "y"  # default vertical

            new_block = f"{base}[axis={axis}]"
            stats["logs"] += 1

        # Ensure new block variant is in palette
        if new_block != base and new_block not in new_palette:
            new_palette[new_block] = len(new_palette)

        processed.append({**b, "block": new_block})

    # ── Pass 2: Stair corner shapes ──
    # Direction vectors: facing -> (front_dz, front_dx), left, right
    _FACING_MAP = {
        "north": {"front": (0, 0, -1), "back": (0, 0, 1),  "left": "west",  "right": "east"},
        "south": {"front": (0, 0, 1),  "back": (0, 0, -1), "left": "east",  "right": "west"},
        "east":  {"front": (1, 0, 0),  "back": (-1, 0, 0), "left": "north", "right": "south"},
        "west":  {"front": (-1, 0, 0), "back": (1, 0, 0),  "left": "south", "right": "north"},
    }

    for i, b in enumerate(processed):
        pos = (b["x"], b["y"], b["z"])
        if pos not in stair_data:
            continue

        sd = stair_data[pos]
        facing = sd["facing"]
        half = sd["half"]
        base = sd["base"]
        shape = "straight"

        fm = _FACING_MAP[facing]
        fdx, fdy, fdz = fm["front"]
        bdx, bdy, bdz = fm["back"]

        # Check front neighbor
        front_pos = (pos[0] + fdx, pos[1] + fdy, pos[2] + fdz)
        front_sd = stair_data.get(front_pos)
        if front_sd and front_sd["half"] == half and front_sd["facing"] != facing:
            if front_sd["facing"] == fm["left"]:
                shape = "outer_left"
            elif front_sd["facing"] == fm["right"]:
                shape = "outer_right"

        # Check back neighbor (inner corners take priority)
        back_pos = (pos[0] + bdx, pos[1] + bdy, pos[2] + bdz)
        back_sd = stair_data.get(back_pos)
        if back_sd and back_sd["half"] == half and back_sd["facing"] != facing:
            if back_sd["facing"] == fm["left"]:
                shape = "inner_left"
            elif back_sd["facing"] == fm["right"]:
                shape = "inner_right"

        new_block = f"{base}[facing={facing},half={half},shape={shape}]"
        if new_block not in new_palette:
            new_palette[new_block] = len(new_palette)
        processed[i] = {**b, "block": new_block}

    # Log stats
    fixed = sum(stats.values())
    if fixed:
        logger.info(f"\033[32m[postprocess] Fixed {fixed} blocks: {stats}\033[0m")

    return new_palette, processed
