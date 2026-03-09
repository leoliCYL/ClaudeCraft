"""
LangGraph StateGraph — orchestrates the multi-agent pipeline.

Graph flow:
    START -> route -> chat -> END
                   |-> build -> image_search -> palette -> trellis_generator -> converter -> END
"""

import logging
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, END, START

from nodes.router import route_intent
from nodes.chat import chat_respond
from nodes.builder import build_respond
from nodes.image_search import search_images
from nodes.palette import extract_palette
from nodes.trellis_generator import generate_mesh
from nodes.converter import convert_to_layers

logger = logging.getLogger(__name__)
THRESHOLD = 0.9


# ---------------------------------------------------------------------------
# Shared state schema
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    # Core
    user_message: str
    chat_history: list
    intent: str
    ai_response: str

    # RAG path (existing schematics)
    schematic_name: Optional[str]
    schematic_path: Optional[str]
    rag_score: Optional[float]

    # Generation pipeline
    reference_images: Optional[list]   # base64 data URLs from image search
    block_palette: Optional[dict]      # {bottom_layer, middle_layer, top_layer}
    combined_blocks: Optional[list]    # voxelized blocks with palette applied
    build_json: Optional[dict]         # full JSON {palette, components, placements}
    build_layers: Optional[dict]       # Y-grouped layers for streaming
    total_layers: Optional[int]        # number of Y layers
    glb_path: Optional[str]            # path to generated GLB file
    obj_path: Optional[str]            # path to generated OBJ file

    # Future
    build_plan: Optional[dict]


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------

def _route_decision(state: AgentState) -> str:
    return state.get("intent", "chat")


def _build_decision(state: AgentState) -> str:
    score = state.get("rag_score", 0.0)
    if state.get("schematic_path") and score >= THRESHOLD:
        logger.info(f"\033[32mRAG score {score:.3f} >= {THRESHOLD} — using existing schematic\033[0m")
        return "rag_hit"
    logger.info(f"\033[32mRAG score {score:.3f} < {THRESHOLD} — entering generation pipeline\033[0m")
    return "generate"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_graph():
    """Compile and return the LangGraph app."""
    graph = StateGraph(AgentState)

    graph.add_node("route", route_intent)
    graph.add_node("chat", chat_respond)
    graph.add_node("build", build_respond)
    graph.add_node("image_search", search_images)
    graph.add_node("palette", extract_palette)
    graph.add_node("trellis_generator", generate_mesh)
    graph.add_node("converter", convert_to_layers)

    graph.add_edge(START, "route")

    graph.add_conditional_edges("route", _route_decision, {
        "chat": "chat",
        "build": "build",
    })
    graph.add_edge("chat", END)

    graph.add_conditional_edges("build", _build_decision, {
        "rag_hit": END,
        "generate": "image_search",
    })

    graph.add_edge("image_search", "palette")
    graph.add_edge("palette", "trellis_generator")
    graph.add_edge("trellis_generator", "converter")
    graph.add_edge("converter", END)

    compiled = graph.compile()
    logger.info("LangGraph agent compiled successfully.")
    return compiled
