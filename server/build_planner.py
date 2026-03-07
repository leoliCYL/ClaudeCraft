import os
import json
import base64
import logging
from pathlib import Path
from typing import List, Optional, TypedDict

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END, START
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------

class BuildPlannerState(TypedDict):
    build_name: str
    block_palette: List[str]
    image_paths: List[str]
    style_analysis: str
    section_plan: str
    build_plan: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0.4,
    )


def _image_to_content_part(path: str) -> dict:
    ext = Path(path).suffix.lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    mime_type = mime_map.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime_type};base64,{b64}"},
    }


def _strip_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # drop opening fence line and closing fence line
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        # drop optional language tag on first line
        if inner and inner[0].strip().lower() in ("json", ""):
            inner = inner[1:]
        text = "\n".join(inner).strip()
    return text


# ---------------------------------------------------------------------------
# LangGraph nodes
# ---------------------------------------------------------------------------

def analyze_images_node(state: BuildPlannerState) -> dict:
    """
    Analyze the inspiration images and extract style, mood, and material cues
    that should inform the Minecraft build.
    """
    image_paths = state["image_paths"]

    if not image_paths:
        return {"style_analysis": "No inspiration images provided. Default to a generic Minecraft aesthetic."}

    content: list = [
        {
            "type": "text",
            "text": (
                "You are a Minecraft build design expert. Carefully examine the inspiration images below. "
                "Describe in detail:\n"
                "- Overall architectural style (medieval, modern, fantasy, rustic, etc.)\n"
                "- Dominant color palette and textures\n"
                "- Structural shapes and patterns (arches, towers, flat roofs, pitched roofs, etc.)\n"
                "- Mood and atmosphere\n"
                "- Spatial organisation (compact vs sprawling, vertical vs horizontal, etc.)\n"
                "- Any notable decorative or functional details to replicate in Minecraft\n\n"
                "Be specific. This analysis will guide a complete Minecraft build plan."
            ),
        }
    ]

    for path in image_paths:
        try:
            content.append(_image_to_content_part(path))
        except Exception as e:
            logger.warning(f"Could not load image '{path}': {e}")

    response = _llm().invoke([HumanMessage(content=content)])
    return {"style_analysis": response.content}


def plan_sections_node(state: BuildPlannerState) -> dict:
    """
    Decide the most appropriate strategy for dividing the build into sections,
    and list those sections with rough size guidance.
    """
    palette_str = ", ".join(state["block_palette"])

    prompt = (
        f"You are a Minecraft build architect.\n\n"
        f"Build name: {state['build_name']}\n"
        f"Available block palette: {palette_str}\n"
        f"Style analysis:\n{state['style_analysis']}\n\n"
        "Choose the best strategy to divide this build into distinct sections. "
        "You may use one or several of the following strategies — pick whatever makes the most "
        "architectural sense for THIS build:\n\n"
        "  • By HEIGHT       – e.g. foundation, ground floor, upper floors, roof\n"
        "  • By FUNCTION     – e.g. entrance, living area, storage, crafting room, sleeping quarters, defense\n"
        "  • By ROOM         – e.g. kitchen, bedroom, great hall, dungeon, treasury, chapel\n"
        "  • By WING/SECTION – e.g. north wing, east tower, central keep, outer wall, gatehouse\n"
        "  • By MATERIAL ZONE– e.g. stone base, timber frame, glass facade, decorative trim\n"
        "  • By PHASE        – e.g. structural core, interior fit-out, exterior details, landscaping\n\n"
        "Output:\n"
        "1. The strategy you chose and why it suits this build.\n"
        "2. A numbered list of sections with a one-sentence purpose and an approximate bounding-box "
        "   size (width × height × depth in blocks) for each section.\n"
        "Keep it concise. Plain text only."
    )

    response = _llm().invoke([HumanMessage(content=prompt)])
    return {"section_plan": response.content}


def generate_build_plan_node(state: BuildPlannerState) -> dict:
    """
    Produce the final structured JSON build plan with all section details.
    """
    prompt = (
        f"You are a Minecraft build architect. Produce a complete build plan as a JSON object.\n\n"
        f"Build name: {state['build_name']}\n"
        f"Available block palette (USE ONLY THESE IDs):\n{json.dumps(state['block_palette'], indent=2)}\n\n"
        f"Style analysis:\n{state['style_analysis']}\n\n"
        f"Section plan:\n{state['section_plan']}\n\n"
        "Rules:\n"
        "- Only include block IDs that appear in the palette above.\n"
        "- Each section's 'blocks' list should contain only the palette blocks most relevant to that section.\n"
        "- Dimensions must be positive integers.\n"
        "- 'description' should explain the section's purpose, appearance, and key construction notes.\n\n"
        "Return ONLY a valid JSON object — no markdown fences, no explanation — matching this schema exactly:\n"
        "{\n"
        '  "build_name": "string",\n'
        '  "style_notes": "string — summary of the style drawn from the inspiration images",\n'
        '  "division_strategy": "string — how and why the build is divided this way",\n'
        '  "sections": [\n'
        "    {\n"
        '      "name": "string",\n'
        '      "blocks": ["minecraft:block_id", ...],\n'
        '      "dimensions": { "width": integer, "height": integer, "depth": integer },\n'
        '      "description": "string"\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    response = _llm().invoke([HumanMessage(content=prompt)])
    raw = _strip_fences(response.content)

    try:
        build_plan = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse build plan JSON: {e}\nRaw output:\n{raw}")
        raise ValueError(f"LLM returned invalid JSON: {e}") from e

    return {"build_plan": build_plan}


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def _build_graph():
    graph = StateGraph(BuildPlannerState)

    graph.add_node("analyze_images", analyze_images_node)
    graph.add_node("plan_sections", plan_sections_node)
    graph.add_node("generate_build_plan", generate_build_plan_node)

    graph.add_edge(START, "analyze_images")
    graph.add_edge("analyze_images", "plan_sections")
    graph.add_edge("plan_sections", "generate_build_plan")
    graph.add_edge("generate_build_plan", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plan_build(
    build_name: str,
    block_palette: List[str],
    image_paths: Optional[List[str]] = None,
) -> dict:
    """
    Run the LangGraph build-planner agent and return a structured JSON build plan.

    Args:
        build_name:    Name for the overall build (e.g. "Medieval Castle").
        block_palette: List of Minecraft block IDs the builder may use.
        image_paths:   Optional list of JPEG/PNG file paths for style inspiration.

    Returns:
        dict with keys: build_name, style_notes, division_strategy, sections
        Each section has: name, blocks, dimensions (width/height/depth), description
    """
    app = _build_graph()

    initial_state: BuildPlannerState = {
        "build_name": build_name,
        "block_palette": block_palette,
        "image_paths": image_paths or [],
        "style_analysis": "",
        "section_plan": "",
        "build_plan": {},
    }

    result = app.invoke(initial_state)
    return result["build_plan"]


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    example_palette = [
        "minecraft:stone",
        "minecraft:cobblestone",
        "minecraft:stone_bricks",
        "minecraft:cracked_stone_bricks",
        "minecraft:mossy_stone_bricks",
        "minecraft:chiseled_stone_bricks",
        "minecraft:oak_planks",
        "minecraft:oak_log",
        "minecraft:oak_stairs",
        "minecraft:oak_slab",
        "minecraft:oak_fence",
        "minecraft:oak_door",
        "minecraft:glass_pane",
        "minecraft:iron_bars",
        "minecraft:torch",
        "minecraft:lantern",
        "minecraft:gravel",
        "minecraft:dirt",
        "minecraft:grass_block",
    ]

    # Any extra CLI args are treated as image paths
    images = sys.argv[1:] if len(sys.argv) > 1 else []

    result = plan_build(
        build_name="Medieval Castle",
        block_palette=example_palette,
        image_paths=images,
    )

    print(json.dumps(result, indent=2))
