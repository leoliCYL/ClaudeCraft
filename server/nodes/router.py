"""
Router node — classifies user intent so the graph can branch.
Uses keyword matching first (free), falls back to LLM for ambiguous cases.
"""

import re
import logging

from langchain_core.messages import SystemMessage, HumanMessage
from lib.llm_factory import get_llm
from prompts.system_prompts import ROUTER_SYSTEM

logger = logging.getLogger(__name__)

_BUILD_KEYWORDS = r'\b(build|construct|create|make|place|load|generate|spawn|put)\b'


def route_intent(state: dict) -> dict:
    """Classify the user's message as 'chat' or 'build'."""
    msg = state["user_message"].lower().strip()

    # Fast keyword check — avoids burning an API call for obvious cases
    if re.search(_BUILD_KEYWORDS, msg):
        logger.info(f"Router (keyword match): '{msg[:50]}...' -> 'build'")
        return {"intent": "build"}

    # For ambiguous messages, use LLM
    try:
        llm = get_llm(temperature=0.0)
        result = llm.invoke([
            SystemMessage(content=ROUTER_SYSTEM),
            HumanMessage(content=state["user_message"]),
        ])
        intent = result.content.strip().lower()
        if intent not in ("chat", "build"):
            intent = "chat"
        logger.info(f"Router (LLM): '{msg[:50]}...' -> '{intent}'")
        return {"intent": intent}
    except Exception as e:
        logger.warning(f"Router LLM failed ({e}), defaulting to 'chat'")
        return {"intent": "chat"}
