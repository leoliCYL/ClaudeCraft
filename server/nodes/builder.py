"""
Builder node — retrieves a matching schematic via RAG and prepares file transfer.
"""

import logging

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from lib.llm_factory import get_llm
from lib.rag import retrieve_schematic
from prompts.system_prompts import BUILD_SYSTEM

logger = logging.getLogger(__name__)


def build_respond(state: dict) -> dict:
    """
    Handle a build request:
    1. Generate a friendly acknowledgement
    2. Use RAG to find the best matching schematic
    3. Set schematic metadata for file transfer
    """
    llm = get_llm(temperature=0.7)

    # Generate the conversational reply
    messages = [SystemMessage(content=BUILD_SYSTEM)]
    for msg in state.get("chat_history", []):
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=state["user_message"]))

    result = llm.invoke(messages)
    reply = result.content.strip()
    logger.info(f"\033[35mBuilder response: {reply[:80]}...\033[0m")

    # RAG retrieval — find the best schematic
    match = retrieve_schematic(state["user_message"])

    schematic_name = None
    schematic_path = None
    rag_score = 0.0

    if match:
        schematic_name = match["name"]
        schematic_path = match["path"]
        rag_score = match.get("score", 0.0)
        logger.info(f"RAG matched schematic: {schematic_name} (score={rag_score:.3f})")
    else:
        logger.warning("No schematic found via RAG for this build request.")

    # Update history
    updated_history = list(state.get("chat_history", []))
    updated_history.append({"role": "user", "content": state["user_message"]})
    updated_history.append({"role": "assistant", "content": reply})
    if len(updated_history) > 20:
        updated_history = updated_history[-20:]

    return {
        "ai_response": reply,
        "chat_history": updated_history,
        "schematic_name": schematic_name,
        "schematic_path": schematic_path,
        "rag_score": rag_score,
    }
