"""
Schematic RAG — indexes .litematic files into a FAISS vector store
using rich descriptions from schematics.json for semantic matching.
"""

import json
import os
import logging
from pathlib import Path
from typing import Optional

from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# Base server directory (lib/ -> server/)
_SERVER_DIR = Path(__file__).parent.parent

# Directories to scan for .litematic files (in priority order)
_SCHEMATIC_DIRS = [
    _SERVER_DIR / ".." / "client" / "run" / "schematics",
    _SERVER_DIR / ".." / "client" / "run" / "litematics",
    _SERVER_DIR / "assets",
]

# JSON metadata file
_METADATA_PATH = _SERVER_DIR / "schematics.json"


def _load_metadata() -> dict:
    """Load schematic descriptions from schematics.json."""
    if not _METADATA_PATH.exists():
        logger.warning(f"No schematics.json found at {_METADATA_PATH}")
        return {}
    with open(_METADATA_PATH, "r") as f:
        return json.load(f)


def _discover_schematics() -> list[Document]:
    """Walk schematic directories and create a Document per .litematic file,
    enriched with descriptions from schematics.json."""
    metadata_map = _load_metadata()
    docs: list[Document] = []
    seen: set[str] = set()

    for directory in _SCHEMATIC_DIRS:
        resolved = directory.resolve()
        if not resolved.is_dir():
            continue
        for file in resolved.glob("*.litematic"):
            name = file.stem
            if name in seen:
                continue
            seen.add(name)

            # Build rich content from JSON metadata, fall back to filename
            entry = metadata_map.get(name, {})
            description = entry.get("description", "")
            tags = entry.get("tags", [])

            if description:
                content = f"{description}"
                if tags:
                    content += f" Tags: {', '.join(tags)}"
            else:
                # Fallback: humanize the filename
                readable = name.replace("-", " ").replace("_", " ")
                content = f"Minecraft schematic: {readable}"

            docs.append(
                Document(
                    page_content=content,
                    metadata={"name": name, "path": str(file)},
                )
            )
            logger.info(f"Indexed schematic: {name} -> '{content[:60]}...'")

    if not docs:
        logger.warning("No .litematic files found in any schematic directory.")
    return docs


def _build_index() -> Optional[FAISS]:
    """Build (or rebuild) the FAISS index over discovered schematics."""
    docs = _discover_schematics()
    if not docs:
        return None

    from lib.llm_factory import get_embeddings

    embeddings = get_embeddings()
    return FAISS.from_documents(docs, embeddings)


# Module-level lazy singleton
_index: Optional[FAISS] = None


def get_index() -> Optional[FAISS]:
    global _index
    if _index is None:
        _index = _build_index()
    return _index


def refresh_index() -> None:
    """Force a re-scan of schematic directories and rebuild the index."""
    global _index
    _index = _build_index()


def retrieve_schematic(query: str, k: int = 1) -> Optional[dict]:
    """
    Find the best-matching schematic for a natural-language query.

    Returns:
        dict with keys 'name', 'path', and 'score' (0-1, higher = better),
        or None if no schematics exist.
    """
    index = get_index()
    if index is None:
        return None

    results = index.similarity_search_with_score(query, k=k)
    if not results:
        return None

    best_doc, distance = results[0]
    # FAISS returns L2 distance — convert to a 0-1 similarity score
    score = 1.0 / (1.0 + distance)
    logger.info(f"\033[32mRAG match for '{query}': {best_doc.metadata['name']} (score={score:.3f})\033[0m")
    return {"name": best_doc.metadata["name"], "path": best_doc.metadata["path"], "score": score}
