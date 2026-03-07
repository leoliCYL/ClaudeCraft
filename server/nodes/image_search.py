"""
Image Search node — finds reference images for the build request.

Input:  user_message (build request)
Output: reference_images (list of image URLs/paths)
"""

import logging

logger = logging.getLogger(__name__)


def search_images(state: dict) -> dict:
    """Search for reference images matching the build request."""
    # TODO: Implement image search (Google Images API, Bing, or local library)
    logger.info(f"[image_search] Searching images for: {state['user_message'][:50]}...")

    return {
        "reference_images": [],  # list of image URLs or paths
    }
