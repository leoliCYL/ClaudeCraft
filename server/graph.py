"""
LangGraph StateGraph — orchestrates the multi-agent pipeline.

Graph flow:
    START -> route -> chat -> END
                   |-> build -> image_search -> palette -> component_planner
                      -> component_builder -> combiner -> converter -> END
"""

import logging
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, END, START

from nodes.router import route_intent
from nodes.chat import chat_respond
from nodes.builder import build_respond
from nodes.image_search import search_images
from nodes.palette import extract_palette
from nodes.component_planner import plan_components
from nodes.component_builder import build_component
from nodes.combiner import combine_components
from nodes.converter import convert_to_layers

logger = logging.getLogger(__name__)


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
    reference_images: Optional[list]           # URLs/paths from image search
    block_palette: Optional[list]              # block IDs + usage hints
    components: Optional[list]                 # component specs from planner
    component_results: Optional[list]          # built component block data
    combined_blocks: Optional[list]            # merged block list
    build_layers: Optional[dict]               # Y-grouped layers for streaming
    total_layers: Optional[int]                # number of Y layers

    # Future
    build_plan: Optional[dict]


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------

def _route_decision(state: AgentState) -> str:
    """Branch to chat or build based on classified intent."""
    return state.get("intent", "chat")


def _build_decision(state: AgentState) -> str:
    """
    After the build node (RAG check):
    - If a schematic was found via RAG with high confidence -> 'rag_hit'
    - Otherwise -> 'generate' (run the generation pipeline)
    """
    score = state.get("rag_score", 0.0)
    if state.get("schematic_path") and score >= 0.7:
        logger.info(f"RAG score {score:.3f} >= 0.7 — using existing schematic")
        return "rag_hit"
    logger.info(f"RAG score {score:.3f} < 0.7 — entering generation pipeline")
    return "generate"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_graph():
    """Compile and return the LangGraph app."""
    graph = StateGraph(AgentState)

    # ── Register nodes ──
    graph.add_node("route", route_intent)
    graph.add_node("chat", chat_respond)
    graph.add_node("build", build_respond)

    # Generation pipeline nodes
    graph.add_node("image_search", search_images)
    graph.add_node("palette", extract_palette)
    graph.add_node("component_planner", plan_components)
    graph.add_node("component_builder", build_component)
    graph.add_node("combiner", combine_components)
    graph.add_node("converter", convert_to_layers)

    # ── Edges ──

    # Entry
    graph.add_edge(START, "route")

    # Route -> chat or build
    graph.add_conditional_edges("route", _route_decision, {
        "chat": "chat",
        "build": "build",
    })
    graph.add_edge("chat", END)

    # Build -> RAG hit (stream existing) or generate (full pipeline)
    graph.add_conditional_edges("build", _build_decision, {
        "rag_hit": END,          # main.py handles streaming the matched file
        "generate": "image_search",
    })

    # Generation pipeline: sequential chain
    graph.add_edge("image_search", "palette")
    graph.add_edge("palette", "component_planner")
    graph.add_edge("component_planner", "component_builder")
    graph.add_edge("component_builder", "combiner")
    graph.add_edge("combiner", "converter")
    graph.add_edge("converter", END)

    compiled = graph.compile()
    logger.info("LangGraph agent compiled successfully.")
    return compiled
