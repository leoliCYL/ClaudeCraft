"""
Image Search node — finds reference images for the build request.

Uses DuckDuckGo image search (no API key required) to find reference images.
Images are kept in memory as base64 data URLs — no disk writes.

Input:  user_message (build request)
Output: reference_images (list of base64 data URL strings)
"""

import logging
import base64
import httpx

from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)


def _download_as_data_url(url: str) -> str | None:
    """Download an image URL and return it as a base64 data URL, or None on failure."""
    try:
        resp = httpx.get(url, timeout=5, follow_redirects=True)
        if resp.status_code != 200:
            return None
        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type:
            return None

        # Normalize MIME type
        if "png" in content_type:
            mime = "image/png"
        elif "webp" in content_type:
            mime = "image/webp"
        else:
            mime = "image/jpeg"

        b64 = base64.b64encode(resp.content).decode()
        return f"data:{mime};base64,{b64}"
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

        for result in results:
            url = result.get("image", "")
            if not url:
                continue
            data_url = _download_as_data_url(url)
            if data_url:
                reference_images.append(data_url)
                logger.info(f"[image_search] Downloaded image from {url[:60]}... ({len(data_url)//1024}KB in RAM)")

    except Exception as e:
        logger.error(f"[image_search] DuckDuckGo search failed: {e}")

    logger.info(f"[image_search] {len(reference_images)} images in memory")

    return {
        "reference_images": reference_images,
    }