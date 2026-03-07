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

# Directories to scan for .litematic files (in priority order)
_SCHEMATIC_DIRS = [
    Path(__file__).parent / ".." / "client" / "run" / "schematics",
    Path(__file__).parent / ".." / "client" / "run" / "litematics",
    Path(__file__).parent / "assets",
]

# JSON metadata file
_METADATA_PATH = Path(__file__).parent / "schematics.json"


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

    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=os.getenv("GEMINI_API_KEY"),
    )
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
        dict with keys 'name' and 'path', or None if no schematics exist.
    """
    index = get_index()
    if index is None:
        return None

    results = index.similarity_search(query, k=k)
    if not results:
        return None

    best = results[0]
    logger.info(f"RAG match for '{query}': {best.metadata['name']}")
    return {"name": best.metadata["name"], "path": best.metadata["path"]}
