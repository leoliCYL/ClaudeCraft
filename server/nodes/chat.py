"""
Chat node — conversational Minecraft assistant.
"""

import os
import logging

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

logger = logging.getLogger(__name__)

_CHAT_SYSTEM = """\
You are a friendly and knowledgeable Minecraft assistant called Claude Craft.
You chat with the player about anything Minecraft-related: tips, strategies,
lore, building advice, redstone, mobs, enchantments, etc.
Keep responses concise (2-3 sentences) since they appear in a small in-game overlay.
Be enthusiastic and helpful!"""


def chat_respond(state: dict) -> dict:
    """Generate a conversational response."""
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0.7,
    )

    # Build message list from history + current message
    messages = [SystemMessage(content=_CHAT_SYSTEM)]

    for msg in state.get("chat_history", []):
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))

    messages.append(HumanMessage(content=state["user_message"]))

    result = llm.invoke(messages)
    reply = result.content.strip()

    logger.info(f"Chat response: {reply[:80]}...")

    # Update history
    updated_history = list(state.get("chat_history", []))
    updated_history.append({"role": "user", "content": state["user_message"]})
    updated_history.append({"role": "assistant", "content": reply})

    # Keep history bounded
    if len(updated_history) > 20:
        updated_history = updated_history[-20:]

    return {
        "ai_response": reply,
        "chat_history": updated_history,
    }
