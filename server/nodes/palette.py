"""
Palette node — analyzes reference images to determine a Minecraft block palette.

Input:  reference_images (from image_search) — list of image file paths
Output: block_palette (list of minecraft block ID strings)
"""

import os
import logging
from PIL import Image
from google import genai

logger = logging.getLogger(__name__)

# Curated list of exactly 200 realistic/architectural Minecraft blocks (1.21.11 Namespaced IDs)
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


def _compress_image(input_path: str, output_path: str, max_size: tuple = (1024, 1024)) -> bool:
    """Resize and compress an image, saving to output_path. Returns True on success."""
    try:
        with Image.open(input_path) as img:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            save_params = {}
            ext = output_path.lower().split(".")[-1]
            if ext in ("jpg", "jpeg"):
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                save_params = {"optimize": True, "quality": 70}
            elif ext == "png":
                save_params = {"optimize": True}
            elif ext == "webp":
                save_params = {"optimize": True, "quality": 70}
            img.save(output_path, **save_params)
        return True
    except Exception as e:
        logger.warning(f"[palette] Failed to compress '{input_path}': {e}")
        return False


def _analyze_images(image_paths: list[str]) -> list[str]:
    """Send compressed images to Gemini and return a list of 15 block IDs."""
    client = genai.Client()
    images = []
    for path in image_paths:
        try:
            images.append(Image.open(path))
        except Exception as e:
            logger.warning(f"[palette] Could not open image {path}: {e}")

    if not images:
        return []

    prompt = f"""Look at these {len(images)} images. I want to recreate the average aesthetic and common themes of these scenes in Minecraft.
Analyze the overall colors, textures, and prominent materials across all the provided images.
Select exactly 15 Minecraft blocks from the specific list below that would make the best, unified architectural palette to build scenes matching this general vibe.

ALLOWED BLOCKS:
{', '.join(MINECRAFT_BLOCKS)}

Output ONLY a numbered list of the 15 blocks, from 1 to 15. Do not include any intro, outro, or explanation. Only choose blocks from the allowed list."""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=images + [prompt],
    )

    blocks = []
    for line in response.text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading "1. " / "1) " numbering
        if line[0].isdigit():
            line = line.split(".", 1)[-1].split(")", 1)[-1].strip()
        if line:
            blocks.append(line)
    return blocks


def extract_palette(state: dict) -> dict:
    """Analyze reference images and extract a Minecraft block palette."""
    reference_images: list[str] = state.get("reference_images", [])
    logger.info(f"[palette] Extracting palette from {len(reference_images)} images...")

    if not reference_images:
        return {"block_palette": []}

    # Compress images into a temp directory before sending to the LLM
    tmp_dir = os.path.join(os.path.dirname(__file__), ".palette_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    compressed_paths = []
    for path in reference_images:
        filename = os.path.basename(path)
        out_path = os.path.join(tmp_dir, "compressed_" + filename)
        if _compress_image(path, out_path):
            compressed_paths.append(out_path)

    if not compressed_paths:
        logger.warning("[palette] No images could be compressed; returning empty palette.")
        return {"block_palette": []}

    try:
        block_palette = _analyze_images(compressed_paths)
    except Exception as e:
        logger.error(f"[palette] AI analysis failed: {e}")
        block_palette = []

    logger.info(f"[palette] Got palette: {block_palette}")
    return {"block_palette": block_palette}
