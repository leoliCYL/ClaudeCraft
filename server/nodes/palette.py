"""
Palette node — analyzes reference images to determine a Minecraft block palette.

Runs BEFORE 3D generation. Only selects block types; block assignment happens
after voxelization in the combiner.

Input:  reference_images (from image_search), user_message
Output: block_palette (dict with bottom_layer, middle_layer, top_layer)
"""

import logging
import json
from lib.llm_factory import get_llm
from prompts.system_prompts import palette_prompt

logger = logging.getLogger(__name__)


def extract_palette(state: dict) -> dict:
    """Analyze reference images (or text description) and extract a Minecraft block palette."""
    reference_images: list[str] = state.get("reference_images", [])
    user_message = state.get("user_message", "")

    logger.info(f"[palette] Selecting block palette from {len(reference_images)} images...")

    llm = get_llm(temperature=0.3)

    content_parts = []
    for data_url in reference_images:
        if data_url and data_url.startswith("data:"):
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": data_url},
            })

    has_images = len(content_parts) > 0
    prompt_text = palette_prompt(user_message, has_images)
    content_parts.append({"type": "text", "text": prompt_text})

    block_palette = {
        "palette": [{"block": "minecraft:stone", "hex": "#7D7D7D"}]
    }

    try:
        from langchain_core.messages import HumanMessage
        result = llm.invoke([HumanMessage(content=content_parts)])
        raw = result.content.strip()
        logger.info(f"[palette] LLM raw response: {raw[:200]}...")

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            raw = raw.rsplit("```", 1)[0]

        mapping = json.loads(raw)
        if "palette" in mapping and isinstance(mapping["palette"], list):
            block_palette["palette"] = mapping["palette"]
        logger.info(f"[palette] Selected palette with {len(block_palette['palette'])} blocks")

    except Exception as e:
        logger.error(f"[palette] LLM palette selection failed: {e}")

    return {"block_palette": block_palette}
