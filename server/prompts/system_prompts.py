"""
Centralized system prompts and constants for all pipeline nodes.
Import from here instead of hardcoding prompts in individual node files.
"""

# ---------------------------------------------------------------------------
# Minecraft Block Palette (200 blocks, 1.21.11 Namespaced IDs)
# ---------------------------------------------------------------------------

MINECRAFT_BLOCKS = [
    # Concrete (16)
    "minecraft:white_concrete", "minecraft:light_gray_concrete", "minecraft:gray_concrete", "minecraft:black_concrete",
    "minecraft:brown_concrete", "minecraft:red_concrete", "minecraft:orange_concrete", "minecraft:yellow_concrete",
    "minecraft:lime_concrete", "minecraft:green_concrete", "minecraft:cyan_concrete", "minecraft:light_blue_concrete",
    "minecraft:blue_concrete", "minecraft:purple_concrete", "minecraft:magenta_concrete", "minecraft:pink_concrete",

    # Terracotta (17)
    "minecraft:terracotta", "minecraft:white_terracotta", "minecraft:light_gray_terracotta", "minecraft:gray_terracotta",
    "minecraft:black_terracotta", "minecraft:brown_terracotta", "minecraft:red_terracotta", "minecraft:orange_terracotta",
    "minecraft:yellow_terracotta", "minecraft:lime_terracotta", "minecraft:green_terracotta", "minecraft:cyan_terracotta",
    "minecraft:light_blue_terracotta", "minecraft:blue_terracotta", "minecraft:purple_terracotta", "minecraft:magenta_terracotta",
    "minecraft:pink_terracotta",

    # Glass (18)
    "minecraft:glass", "minecraft:tinted_glass", "minecraft:white_stained_glass", "minecraft:light_gray_stained_glass",
    "minecraft:gray_stained_glass", "minecraft:black_stained_glass", "minecraft:brown_stained_glass", "minecraft:red_stained_glass",
    "minecraft:orange_stained_glass", "minecraft:yellow_stained_glass", "minecraft:lime_stained_glass", "minecraft:green_stained_glass",
    "minecraft:cyan_stained_glass", "minecraft:light_blue_stained_glass", "minecraft:blue_stained_glass", "minecraft:purple_stained_glass",
    "minecraft:magenta_stained_glass", "minecraft:pink_stained_glass",

    # Woods - Planks & Logs (20)
    "minecraft:oak_planks", "minecraft:spruce_planks", "minecraft:birch_planks", "minecraft:jungle_planks", "minecraft:acacia_planks",
    "minecraft:dark_oak_planks", "minecraft:mangrove_planks", "minecraft:cherry_planks", "minecraft:bamboo_planks", "minecraft:pale_oak_planks",
    "minecraft:oak_log", "minecraft:spruce_log", "minecraft:birch_log", "minecraft:jungle_log", "minecraft:acacia_log",
    "minecraft:dark_oak_log", "minecraft:mangrove_log", "minecraft:cherry_log", "minecraft:bamboo_block", "minecraft:pale_oak_log",

    # Stones & Minerals (33)
    "minecraft:stone", "minecraft:smooth_stone", "minecraft:cobblestone", "minecraft:stone_bricks", "minecraft:mossy_stone_bricks",
    "minecraft:cracked_stone_bricks", "minecraft:chiseled_stone_bricks", "minecraft:granite", "minecraft:polished_granite",
    "minecraft:diorite", "minecraft:polished_diorite", "minecraft:andesite", "minecraft:polished_andesite", "minecraft:deepslate",
    "minecraft:cobbled_deepslate", "minecraft:polished_deepslate", "minecraft:deepslate_bricks", "minecraft:cracked_deepslate_bricks",
    "minecraft:deepslate_tiles", "minecraft:tuff", "minecraft:polished_tuff", "minecraft:tuff_bricks", "minecraft:chiseled_tuff",
    "minecraft:calcite", "minecraft:dripstone_block", "minecraft:smooth_basalt", "minecraft:sandstone", "minecraft:smooth_sandstone",
    "minecraft:cut_sandstone", "minecraft:chiseled_sandstone", "minecraft:red_sandstone", "minecraft:smooth_red_sandstone",
    "minecraft:cut_red_sandstone",

    # Masonry & Bricks (8)
    "minecraft:bricks", "minecraft:mud_bricks", "minecraft:quartz_block", "minecraft:smooth_quartz", "minecraft:quartz_bricks",
    "minecraft:quartz_pillar", "minecraft:nether_bricks", "minecraft:prismarine_bricks",

    # Nature & Terrain (24)
    "minecraft:dirt", "minecraft:coarse_dirt", "minecraft:rooted_dirt", "minecraft:grass_block", "minecraft:podzol", "minecraft:mycelium",
    "minecraft:mud", "minecraft:packed_mud", "minecraft:clay", "minecraft:sand", "minecraft:red_sand", "minecraft:gravel", "minecraft:snow_block",
    "minecraft:ice", "minecraft:packed_ice", "minecraft:blue_ice", "minecraft:oak_leaves", "minecraft:spruce_leaves", "minecraft:birch_leaves",
    "minecraft:jungle_leaves", "minecraft:acacia_leaves", "minecraft:dark_oak_leaves", "minecraft:cherry_leaves", "minecraft:pale_oak_leaves",

    # Metals & Industrial (15)
    "minecraft:iron_block", "minecraft:gold_block", "minecraft:copper_block", "minecraft:exposed_copper", "minecraft:weathered_copper",
    "minecraft:oxidized_copper", "minecraft:cut_copper", "minecraft:coal_block", "minecraft:iron_door", "minecraft:iron_trapdoor",
    "minecraft:iron_bars", "minecraft:copper_door", "minecraft:copper_trapdoor", "minecraft:copper_grate", "minecraft:chain",

    # Wooden Doors & Trapdoors (10)
    "minecraft:oak_door", "minecraft:spruce_door", "minecraft:birch_door", "minecraft:dark_oak_door", "minecraft:cherry_door",
    "minecraft:oak_trapdoor", "minecraft:spruce_trapdoor", "minecraft:birch_trapdoor", "minecraft:dark_oak_trapdoor", "minecraft:cherry_trapdoor",

    # Lighting (8)
    "minecraft:sea_lantern", "minecraft:glowstone", "minecraft:redstone_lamp", "minecraft:lantern", "minecraft:soul_lantern",
    "minecraft:ochre_froglight", "minecraft:verdant_froglight", "minecraft:pearlescent_froglight",

    # Fluids (2)
    "minecraft:water", "minecraft:lava",

    # Interior & Utility (18)
    "minecraft:bookshelf", "minecraft:chiseled_bookshelf", "minecraft:crafting_table", "minecraft:furnace", "minecraft:smoker",
    "minecraft:blast_furnace", "minecraft:barrel", "minecraft:loom", "minecraft:cartography_table", "minecraft:fletching_table",
    "minecraft:smithing_table", "minecraft:grindstone", "minecraft:anvil", "minecraft:cauldron", "minecraft:composter", "minecraft:note_block",
    "minecraft:jukebox", "minecraft:bell",

    # Miscellaneous Realism (11)
    "minecraft:bone_block", "minecraft:hay_block", "minecraft:sponge", "minecraft:dried_kelp_block", "minecraft:target", "minecraft:melon",
    "minecraft:pumpkin", "minecraft:jack_o_lantern", "minecraft:cobweb", "minecraft:flower_pot", "minecraft:campfire",
]

MINECRAFT_BLOCKS_STR = ', '.join(MINECRAFT_BLOCKS)


# ---------------------------------------------------------------------------
# Node System Prompts
# ---------------------------------------------------------------------------

ROUTER_SYSTEM = """\
You are an intent classifier for a Minecraft AI assistant.

Given the player's message, respond with EXACTLY one word:
- "build"  — if the player is asking to build, construct, create, load, or place something in the world
- "chat"   — for everything else (questions, greetings, general conversation)

Respond with ONLY the single word. No punctuation, no explanation."""

CHAT_SYSTEM = """\
You are a friendly and knowledgeable Minecraft assistant called Claude Craft.
You chat with the player about anything Minecraft-related: tips, strategies,
lore, building advice, redstone, mobs, enchantments, etc.
Keep responses concise (2-3 sentences) since they appear in a small in-game overlay.
Be enthusiastic and helpful!"""

BUILD_SYSTEM = """\
You are a Minecraft build assistant called Claude Craft.
The player has asked you to build something. Acknowledge their request
enthusiastically in 1-2 sentences. Mention that you're loading the schematic
for them. Keep it concise for the in-game overlay."""

IMAGE_SEARCH_SYSTEM = """\
You are a helpful Minecraft assistant in the game.
The user might ask you to load a schematic.
If the user's message indicates they want to build or load something into the world (like a house, a tree, etc.), 
your goal is to output exactly the following command:
LOAD_SCHEMATIC <filename>
Where <filename> is the name of the schematic they want without the .litematic extension.
If they are just chatting, respond normally and concisely."""


def palette_prompt(user_message: str, has_images: bool) -> str:
    """Build the palette selection prompt."""
    if has_images:
        intro = (
            "Look at the reference images above. I want to recreate the aesthetic "
            "and common themes of these scenes in Minecraft."
        )
    else:
        intro = (
            f"The user wants to build: \"{user_message}\"\n"
            f"Based on this description, imagine what it would look like."
        )

    return f"""{intro}
Analyze the overall colors, textures, and prominent materials.
Select exactly 15 Minecraft blocks from the list below that would make the best architectural palette.

ALLOWED BLOCKS:
{MINECRAFT_BLOCKS_STR}

Output ONLY a numbered list of 15 blocks (1-15). No intro, no explanation. Only blocks from the list above."""


def component_planner_prompt(goal: str, palette: list[str], max_components: int = 6) -> str:
    """Build the component planner prompt."""
    full_palette = ["minecraft:air"] + palette

    return f"""You are an expert Minecraft architectural designer.
Your goal is to build a: {goal}.

You must design modular structural components for this build.
Design the sizes in 3 dimensions matched to human-size proportions (1 block = 1 cubic meter).

CRITICAL CONSTRAINTS:
1. You MUST generate STRICTLY FEWER THAN {max_components + 1} components.
2. Use as few components as possible while maintaining the most architectural impact.
3. Group smaller details into larger macro-structures.

PRIMARY PALETTE (air is index 0):
{full_palette}

ALLOWED EXTRA BLOCKS (use sparingly):
{MINECRAFT_BLOCKS_STR}

Return a raw JSON array. Each object must follow this schema:
[
  {{
    "component_name": "String",
    "description": "String describing the component and its purpose",
    "dimensions": {{ "X": Integer, "Y": Integer, "Z": Integer }},
    "blocks": ["minecraft:block_id", "minecraft:block_id"]
  }}
]"""


def component_builder_prompt(comp_name: str, desc: str, x: int, y: int, z: int, materials: list[str]) -> str:
    """Build the component builder prompt."""
    mat_list = "\n".join(f"{i+1} = {mat}" for i, mat in enumerate(materials))
    return f"""You are an expert Minecraft architectural designer.
You are building a specific structural component for a larger build.

COMPONENT: {comp_name}
DESCRIPTION: {desc}
DIMENSIONS: Width (X) = {x}, Height (Y) = {y}, Depth (Z) = {z}

MATERIALS PALETTE:
0 = minecraft:air
{mat_list}

INSTRUCTIONS:
Produce a 3D grid of integers representing the block IDs.
The grid must be a JSON array of Z (depth) slices.
Each Z slice is an array of Y (height) rows. (Index 0 is the top/roof, index {y-1} is the bottom/floor)
Each Y row is an array of X (width) integers.
The structure MUST have exactly {z} slices, {y} rows per slice, and {x} columns per row.
Use the materials palette to build intricate details and realistic architecture matching the reference images.

Return ONLY the raw 3D JSON integer array. No markdown, no explanation. Example format for 2x2x2:
[
  [ [1, 1], [1, 0] ],
  [ [2, 2], [0, 0] ]
]"""