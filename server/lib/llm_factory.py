"""
LLM Factory — centralized LLM creation, switchable via environment variables.

Environment variables:
    LLM_PROVIDER    "gemini" (default) | "openai"
    LLM_MODEL       Model name (default: provider-dependent)
    GEMINI_API_KEY   Required when provider is "gemini"
    OPENAI_API_KEY   Required when provider is "openai"
    OPENAI_BASE_URL  Optional custom base URL for OpenAI-compatible endpoints
"""

import os
import logging

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "gemini": "gemini-2.0-flash-lite",
    "openai": "gpt-4o-mini",
}


def get_llm(*, temperature: float = 0.7):
    """
    Return a LangChain Chat LLM based on environment configuration.

    Usage:
        from lib.llm_factory import get_llm
        llm = get_llm(temperature=0.0)
        result = llm.invoke(messages)
    """
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    model = os.getenv("LLM_MODEL", _DEFAULTS.get(provider, _DEFAULTS["gemini"]))

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", None)

        kwargs = {
            "model": model,
            "api_key": api_key,
            "temperature": temperature,
        }
        if base_url:
            kwargs["base_url"] = base_url

        logger.info(f"LLM: OpenAI-compatible | model={model} | base_url={base_url or 'default'}")
        return ChatOpenAI(**kwargs)

    else:  # gemini (default)
        from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = os.getenv("GEMINI_API_KEY", "")
        logger.info(f"LLM: Google Gemini | model={model}")
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            temperature=temperature,
        )


def get_embeddings():
    """
    Return a LangChain Embeddings model based on environment configuration.

    Usage:
        from lib.llm_factory import get_embeddings
        embeddings = get_embeddings()
    """
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", None)
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        logger.info(f"Embeddings: OpenAI | base_url={base_url or 'default'}")
        return OpenAIEmbeddings(**kwargs)

    else:  # gemini
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        api_key = os.getenv("GEMINI_API_KEY", "")
        logger.info("Embeddings: Google Gemini | model=gemini-embedding-001")
        return GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=api_key,
        )
