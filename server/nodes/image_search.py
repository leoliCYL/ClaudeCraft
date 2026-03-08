"""
Image Search node — finds reference images for the build request.

Uses SerpApi Google Images Search to find reference images.
Images are kept in memory as base64 data URLs — no disk writes.

Input:  user_message (build request)
Output: reference_images (list of base64 data URL strings)
"""

import os
import logging
import base64
import httpx

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
    """Search for reference images matching the build request using SerpApi."""
    prompt = state.get("user_message", "")
    query = f"{prompt} minecraft build"
    logger.info(f"\033[32m[image_search] Searching SerpApi images for: {query[:60]}...\033[0m")

    reference_images = []
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        logger.error("[image_search] SERPAPI_API_KEY not found in environment!")
        return {"reference_images": []}

    try:
        params = {
            "engine": "google_images",
            "q": query,
            "api_key": api_key,
            "num": 5
        }
        resp = httpx.get("https://serpapi.com/search", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("images_results", [])[:5]
        logger.info(f"[image_search] Got {len(results)} image results from SerpApi")

        for result in results:
            url = result.get("original", "")
            if not url:
                continue
            data_url = _download_as_data_url(url)
            if data_url:
                reference_images.append({
                    "url": url,
                    "data": data_url
                })
                logger.info(f"[image_search] Downloaded image from {url[:60]}... ({len(data_url)//1024}KB in RAM)")

    except Exception as e:
        logger.error(f"[image_search] SerpApi search failed: {e}")

    logger.info(f"[image_search] {len(reference_images)} images in memory")

    return {
        "reference_images": reference_images,
    }