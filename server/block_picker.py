import os
from PIL import Image
from google import genai
from dotenv import load_dotenv

# Load the environment variables from the .env file
load_dotenv()

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
    "minecraft:pumpkin", "minecraft:jack_o_lantern", "minecraft:cobweb", "minecraft:flower_pot", "minecraft:campfire"
]

def compress_image(input_filename, output_filename, max_size=(1024, 1024)):
    """
    Compresses an image from the 'images' folder, maintains aspect ratio, 
    and reduces the file size. Returns True if successful, False otherwise.
    """
    folder_name = "images"
    input_path = os.path.join(folder_name, input_filename)
    output_path = os.path.join(folder_name, output_filename)

    try:
        with Image.open(input_path) as img:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            save_params = {}
            file_extension = output_filename.lower().split('.')[-1]
            
            if file_extension in ['jpg', 'jpeg']:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                save_params = {"optimize": True, "quality": 70} 
            elif file_extension == 'png':
                save_params = {"optimize": True}
            elif file_extension == 'webp':
                save_params = {"optimize": True, "quality": 70}

            img.save(output_path, **save_params)
            
            original_size = os.path.getsize(input_path) / 1024
            new_size = os.path.getsize(output_path) / 1024
            
            print(f"Compressed '{input_filename}': {original_size:.1f} KB -> {new_size:.1f} KB")
            return True
            
    except Exception as e:
        print(f"Failed to compress '{input_filename}': {e}")
        return False

def analyze_images_with_llm(image_paths):
    """
    Sends multiple compressed images to the AI to find an average block palette.
    """
    if "GEMINI_API_KEY" not in os.environ:
        print("Error: Could not find GEMINI_API_KEY. Make sure your .env file is set up correctly.")
        return

    print(f"\nSending {len(image_paths)} images to the AI for batch analysis...")

    client = genai.Client()
    
    # Load all images into memory for the API request
    image_objects = []
    for path in image_paths:
        try:
            image_objects.append(Image.open(path))
        except Exception as e:
            print(f"Error opening {path} for AI analysis: {e}")
            return

    # The prompt explicitly asks to synthesize an average palette based on ALL images
    prompt = f"""
Look at these {len(image_paths)} images. I want to recreate the average aesthetic and common themes of these scenes in Minecraft.
Analyze the overall colors, textures, and prominent materials across all the provided images.
Select exactly 15 Minecraft blocks from the specific list below that would make the best, unified architectural palette to build scenes matching this general vibe.

ALLOWED BLOCKS:
{', '.join(MINECRAFT_BLOCKS)}

Output ONLY a numbered list of the 15 blocks, from 1 to 15. Do not include any intro, outro, or explanation. Only choose blocks from the allowed list.
"""

    # We pass the list of PIL Image objects followed by the text prompt
    contents_payload = image_objects + [prompt]

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents_payload
        )
        
        print(f"\n--- AI Generated Average Palette for the 5 Scenes ---")
        print(response.text.strip())
        
    except Exception as e:
        print(f"An error occurred while connecting to the AI: {e}")

if __name__ == "__main__":
    folder_name = "images"
    
    if not os.path.exists(folder_name):
        print(f"Creating '{folder_name}' folder. Please place your images inside and run again.")
        os.makedirs(folder_name)
        exit()

    # Find valid uncompressed images in the folder
    valid_extensions = ('.png', '.jpg', '.jpeg', '.webp')
    all_files = os.listdir(folder_name)
    
    # Filter for images and ignore ones that are already prefixed with 'compressed_'
    raw_images = [f for f in all_files 
                  if f.lower().endswith(valid_extensions) and not f.startswith("compressed_")]

    if len(raw_images) < 5:
        print(f"Warning: Found only {len(raw_images)} uncompressed images in '{folder_name}'. Ensure you have at least 5.")
        # We'll proceed with however many it found, up to 5
    
    images_to_process = raw_images[:5]
    compressed_image_paths = []

    print(f"Found {len(images_to_process)} images to process.")

    # Compress the selected images
    for img_name in images_to_process:
        output_name = "compressed_" + img_name
        success = compress_image(img_name, output_name)
        
        if success:
            compressed_image_paths.append(os.path.join(folder_name, output_name))

    # Run AI analysis on the compressed output
    if compressed_image_paths:
        analyze_images_with_llm(compressed_image_paths)
    else:
        print("No images were successfully compressed to analyze.")
