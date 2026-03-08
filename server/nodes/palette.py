"""
Palette node — analyzes reference images to determine a Minecraft block palette.

Input:  reference_images (from image_search) — list of base64 data URL strings
Output: block_palette (list of minecraft block ID strings)
"""

import logging
from lib.llm_factory import get_llm
from prompts.system_prompts import palette_prompt

logger = logging.getLogger(__name__)


def _parse_block_list(text: str) -> list[str]:
    """Parse a numbered list of blocks from LLM output."""
    blocks = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if line[0].isdigit():
            line = line.split(".", 1)[-1].split(")", 1)[-1].strip()
        line = line.strip("`'\"")
        if line and line.startswith("minecraft:"):
            blocks.append(line)
    return blocks


def extract_palette(state: dict) -> dict:
    """Analyze reference images (or text description) and extract a Minecraft block palette."""
    reference_images: list[str] = state.get("reference_images", [])
    user_message = state.get("user_message", "")
    logger.info(f"[palette] Extracting palette from {len(reference_images)} images...")

    llm = get_llm(temperature=0.3)

    # Images are already base64 data URLs from image_search — use directly
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

    try:
        from langchain_core.messages import HumanMessage
        result = llm.invoke([HumanMessage(content=content_parts)])
        raw = result.content
        logger.info(f"[palette] LLM raw response: {raw[:200]}...")
        block_palette = _parse_block_list(raw)
    except Exception as e:
        logger.error(f"[palette] LLM analysis failed: {e}")
        block_palette = []

    logger.info(f"\033[32m[palette] Got {len(block_palette)} blocks: {block_palette}\033[0m")
    return {"block_palette": block_palette}
