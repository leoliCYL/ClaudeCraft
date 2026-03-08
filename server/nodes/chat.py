"""
Chat node — conversational Minecraft assistant.
"""

import logging

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from lib.llm_factory import get_llm
from prompts.system_prompts import CHAT_SYSTEM

logger = logging.getLogger(__name__)


def chat_respond(state: dict) -> dict:
    """Generate a conversational response."""
    llm = get_llm(temperature=0.7)

    # Build message list from history + current message
    messages = [SystemMessage(content=CHAT_SYSTEM)]

    for msg in state.get("chat_history", []):
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))

    messages.append(HumanMessage(content=state["user_message"]))

    result = llm.invoke(messages)
    reply = result.content.strip()

    logger.info(f"\033[35mChat response: {reply[:80]}...\033[0m")

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
