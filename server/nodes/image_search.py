"""
Image Search node — finds reference images for the build request.

Uses DuckDuckGo image search (no API key required) to find reference images,
downloads them to a temp directory, and passes local paths downstream.

Input:  user_message (build request)
Output: reference_images (list of local image file paths)
"""

import logging
import os
import tempfile
import httpx

from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

# Temp directory for downloaded images (persists for the process lifetime)
_IMG_DIR = os.path.join(tempfile.gettempdir(), "claudecraft_images")
os.makedirs(_IMG_DIR, exist_ok=True)


def _download_image(url: str, idx: int) -> str | None:
    """Download an image URL to a local temp file. Returns path or None."""
    try:
        resp = httpx.get(url, timeout=5, follow_redirects=True)
        if resp.status_code != 200:
            return None
        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type:
            return None

        ext = ".jpg"
        if "png" in content_type:
            ext = ".png"
        elif "webp" in content_type:
            ext = ".webp"

        path = os.path.join(_IMG_DIR, f"ref_{idx}{ext}")
        with open(path, "wb") as f:
            f.write(resp.content)
        return path
    except Exception as e:
        logger.debug(f"[image_search] Failed to download {url}: {e}")
        return None


def search_images(state: dict) -> dict:
    """Search for reference images matching the build request."""
    prompt = state.get("user_message", "")
    query = f"{prompt} minecraft build"
    logger.info(f"\033[32m[image_search] Searching DuckDuckGo images for: {query[:60]}...\033[0m")

    reference_images = []

    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=5))

        logger.info(f"[image_search] Got {len(results)} image results from DDG")

        for i, result in enumerate(results):
            url = result.get("image", "")
            if not url:
                continue
            local_path = _download_image(url, i)
            if local_path:
                reference_images.append(local_path)
                logger.info(f"[image_search] Downloaded: {local_path}")

    except Exception as e:
        logger.error(f"[image_search] DuckDuckGo search failed: {e}")

    logger.info(f"[image_search] {len(reference_images)} images downloaded")

    return {
        "reference_images": reference_images,
    }