"""
Builder node — retrieves a matching schematic via RAG and prepares file transfer.
"""

import os
import logging

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from rag import retrieve_schematic

logger = logging.getLogger(__name__)

_BUILD_SYSTEM = """\
You are a Minecraft build assistant called Claude Craft.
The player has asked you to build something. Acknowledge their request
enthusiastically in 1-2 sentences. Mention that you're loading the schematic
for them. Keep it concise for the in-game overlay."""


def build_respond(state: dict) -> dict:
    """
    Handle a build request:
    1. Generate a friendly acknowledgement
    2. Use RAG to find the best matching schematic
    3. Set schematic metadata for file transfer
    """
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0.7,
    )

    # Generate the conversational reply
    messages = [SystemMessage(content=_BUILD_SYSTEM)]
    for msg in state.get("chat_history", []):
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=state["user_message"]))

    result = llm.invoke(messages)
    reply = result.content.strip()
    logger.info(f"Builder response: {reply[:80]}...")

    # RAG retrieval — find the best schematic
    match = retrieve_schematic(state["user_message"])

    schematic_name = None
    schematic_path = None

    if match:
        schematic_name = match["name"]
        schematic_path = match["path"]
        logger.info(f"RAG matched schematic: {schematic_name} at {schematic_path}")
    else:
        logger.warning("No schematic found via RAG for this build request.")
        reply += "\n\nI couldn't find a matching schematic in my library, sorry!"

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
    }
