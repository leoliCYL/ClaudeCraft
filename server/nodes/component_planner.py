import json
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
"""
Component Planner node — breaks a build into components using palette + images.

Input:  user_message, reference_images, block_palette
Output: components (list of component specs to build in parallel)
"""

import logging

logger = logging.getLogger(__name__)

# The comprehensive list of available blocks
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

def generate_build_components(api_key: str, goal: str, initial_palette: list):
    """
    Generates simplified Minecraft build components using Gemini, saves them to JSON, 
    prints them to the terminal, and returns the updated block palette hash map.
    """
    if len(initial_palette) != 15:
        print("Warning: Initial palette does not have exactly 15 blocks.")

    # Inject air as the very first block (index 0), shifting everything else up
    full_palette = ["minecraft:air"] + initial_palette

    # Initialize the new Client
    client = genai.Client(api_key=api_key)

    # Construct the strict prompt with the new constraints
    prompt = f"""
    You are an expert Minecraft architectural designer.
    Your goal is to build a: {goal}.
    
    You must design modular structural components for this build. 
    Design the sizes in 3 dimensions matched to human-size proportions (Assume 1 block = 1 cubic meter).
    
    CRITICAL CONSTRAINTS:
    1. You MUST generate STRICTLY FEWER THAN 10 components. 
    2. Use as few components as possible while maintaining the most architectural impact. 
    3. Group smaller details into larger macro-structures. Get rid of unnecessary or highly specific micro-components.
    
    PRIMARY PALETTE (Try to use mostly these 16 blocks, note air is index 0):
    {full_palette}
    
    ALLOWED EXTRA BLOCKS (Use sparingly only if necessary to complete the theme):
    {MINECRAFT_BLOCKS}

    OUTPUT FORMAT:
    You must return a raw JSON array containing component objects. DO NOT wrap it in markdown block quotes.
    Each object in the array must strictly follow this exact schema:
    [
      {{
        "component_name": "String",
        "description": "String describing the component and its purpose",
        "dimensions": {{
            "X": Integer,
            "Y": Integer,
            "Z": Integer
        }},
        "blocks": [
            "String (exact minecraft ID)", 
            "String (exact minecraft ID)"
        ]
      }}
    ]
    """

    print(f"Asking Gemini to design a {goal}...")
    
    # Generate content using the fast Flash model to avoid quota limits
    response = client.models.generate_content(
        model='gemini-2.5-flash', 
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )

    try:
        components = json.loads(response.text)
    except json.JSONDecodeError:
        print("Failed to parse JSON. Raw output was:")
        print(response.text)
        return None, None

    # Limit to maximum 9 components just in case the LLM ignored the instruction
    if len(components) >= 10:
        print(f"Warning: Model generated {len(components)} components. Truncating to 9.")
        components = components[:9]

    # Initialize our palette hash map using the full palette (starts with air at 0)
    palette_map = {i: block for i, block in enumerate(full_palette)}
    
    # Create a reverse map for quick lookups
    reverse_palette = {block: i for i, block in enumerate(full_palette)}
    next_index = len(full_palette) # Will start at 16

    # Create a directory to store the JSON files
    output_dir = f"{goal.replace(' ', '_').lower()}_components"
    os.makedirs(output_dir, exist_ok=True)

    print(f"\nProcessing {len(components)} components...\n")

    # Process components, print to terminal, update palette, and save to files
    for comp in components:
        # Print the simplified JSON to the terminal
        print(f"--- {comp.get('component_name', 'Unknown Component')} ---")
        print(json.dumps(comp, indent=2))
        print("-" * 40 + "\n")

        # Update palette (blocks array is now just a simple list of strings)
        for b_type in comp.get('blocks', []):
            if b_type and b_type not in reverse_palette:
                print(f"[*] Adding new block to palette map: {b_type} at index {next_index}")
                palette_map[next_index] = b_type
                reverse_palette[b_type] = next_index
                next_index += 1

        # Save component to a JSON file
        safe_name = comp.get('component_name', 'unnamed').replace(' ', '_').lower()
        filepath = os.path.join(output_dir, f"{safe_name}.json")
        
        with open(filepath, 'w') as f:
            json.dump(comp, f, indent=4)

    print("\nFinal Palette Map:")
    for idx, block_id in palette_map.items():
        print(f"  palette[{idx}] = '{block_id}'")

    return palette_map, components

def plan_components(state: dict) -> dict:
    """Decompose the build into independent components that can be built in parallel."""
    logger.info(
        f"[component_planner] Planning components with {len(state.get('block_palette', []))} blocks..."
    )

    goal = state.get("user_message", "").strip()
    initial_palette = state.get("block_palette", [])

    if not goal:
        logger.warning("[component_planner] No user_message found in state.")
        return {"components": []}

    if not initial_palette:
        logger.warning("[component_planner] No block_palette found in state.")
        return {"components": []}

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        logger.error("[component_planner] GEMINI_API_KEY not found.")
        return {"components": []}

    try:
        palette_map, generated_components = generate_build_components(
            api_key=api_key,
            goal=goal,
            initial_palette=initial_palette
        )

        if not generated_components:
            logger.warning("[component_planner] No components were generated.")
            return {"components": []}

        logger.info(
            f"[component_planner] Generated {len(generated_components)} components successfully."
        )

        return {
            "components": generated_components,
            "palette_map": palette_map
        }

    except Exception as e:
        logger.error(f"[component_planner] Failed to generate components: {e}", exc_info=True)
        return {"components": []}

if __name__ == "__main__":
    # Load the variables from the .env file in the same directory
    load_dotenv()
    
    # Safely grab the API key from the environment
    MY_API_KEY = os.getenv("GEMINI_API_KEY")
    
    BUILD_GOAL = "Medieval Castle Gatehouse"
    
    MY_15_BLOCKS = [
        "minecraft:stone_bricks", "minecraft:cracked_stone_bricks", "minecraft:mossy_stone_bricks",
        "minecraft:cobblestone", "minecraft:stone", "minecraft:spruce_planks", "minecraft:spruce_log",
        "minecraft:spruce_trapdoor", "minecraft:iron_bars", "minecraft:iron_door", "minecraft:lantern",
        "minecraft:chain", "minecraft:gravel", "minecraft:dirt", "minecraft:coarse_dirt"
    ]

    # Verify the key was loaded successfully before calling the API
    if MY_API_KEY:
        final_palette, generated_components = generate_build_components(
            api_key=MY_API_KEY, 
            goal=BUILD_GOAL, 
            initial_palette=MY_15_BLOCKS
        )
        if generated_components:
            print("\nProcess complete! Files saved to your folder.")
    else:
        print("Error: Could not find GEMINI_API_KEY. Please ensure your .env file is set up correctly.")
