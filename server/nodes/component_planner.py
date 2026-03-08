"""
Component Planner node — breaks a build into components using palette + images.

Input:  user_message, block_palette
Output: components (list of component specs), palette_map (idx -> block name)
"""

import os
import json
import logging

from langchain_core.messages import HumanMessage
from lib.llm_factory import get_llm
from prompts.system_prompts import MINECRAFT_BLOCKS, component_planner_prompt

logger = logging.getLogger(__name__)


def plan_components(state: dict) -> dict:
    """Decompose the build into independent components that can be built in parallel."""
    initial_palette = state.get("block_palette", [])
    goal = state.get("user_message", "").strip()

    logger.info(f"[component_planner] Planning components with {len(initial_palette)} blocks...")

    if not goal or not initial_palette:
        logger.warning("[component_planner] Missing user_message or block_palette.")
        return {"components": []}

    # Read max components from env, default to 6 if not set
    max_comps = int(os.getenv("MAX_COMPONENTS", 6))

    # Build the prompt
    prompt_text = component_planner_prompt(goal, initial_palette, max_comps)

    reference_images = state.get("reference_images", [])
    content_parts = []
    for item in reference_images:
        data_url = item.get("data") if isinstance(item, dict) else item
        if data_url and data_url.startswith("data:"):
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": data_url},
            })

    content_parts.append({"type": "text", "text": prompt_text})

    # Use the centralized LLM factory
    llm = get_llm(temperature=0.7)

    try:
        result = llm.invoke([HumanMessage(content=content_parts)])
        raw = result.content.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            raw = raw.rsplit("```", 1)[0]

        components = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"[component_planner] Failed to parse LLM JSON: {e}")
        logger.debug(f"[component_planner] Raw response: {raw[:500]}")
        return {"components": []}
    except Exception as e:
        logger.error(f"[component_planner] LLM call failed: {e}")
        return {"components": []}

    # Cap at MAX_COMPONENTS
    if len(components) > max_comps:
        logger.warning(f"[component_planner] Got {len(components)} components, truncating to {max_comps}")
        components = components[:max_comps]

    # Build palette_map: {index: block_name}
    # Air at index 0, then the 15 palette blocks, then any extras from components
    full_palette = ["minecraft:air"] + initial_palette
    palette_map = {i: block for i, block in enumerate(full_palette)}
    reverse = {block: i for i, block in enumerate(full_palette)}
    next_idx = len(full_palette)

    for comp in components:
        for block_name in comp.get("blocks", []):
            if block_name and block_name not in reverse:
                palette_map[next_idx] = block_name
                reverse[block_name] = next_idx
                next_idx += 1

    logger.info(
        f"\033[32m[component_planner] Generated {len(components)} components, "
        f"palette has {len(palette_map)} entries\033[0m"
    )

    for comp in components:
        logger.info(f"  • {comp.get('component_name', '?')} "
                     f"({comp.get('dimensions', {}).get('X', '?')}x"
                     f"{comp.get('dimensions', {}).get('Y', '?')}x"
                     f"{comp.get('dimensions', {}).get('Z', '?')})")

    return {
        "components": components,
        "palette_map": palette_map,
    }
