"""
Image Search node — finds reference images for the build request.

Input:  user_message (build request)
Output: reference_images (list of image URLs/paths)
"""

import logging
import re

logger = logging.getLogger(__name__)

# Perplexity Setup (Using OpenAI-compatible SDK)
PPLX_API_KEY = os.getenv("PERPLEXITY_API_KEY")
pplx_client = OpenAI(api_key=PPLX_API_KEY, base_url="https://api.perplexity.ai") if PPLX_API_KEY else None

# --- Constants & Helpers ---
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
URL_REGEX = re.compile(r'(https?://[^\s]+)', re.IGNORECASE)

def extract_image_urls(text: str) -> list[str]:
    urls = URL_REGEX.findall(text)
    return [url for url in urls if any(url.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)]

def search_images(state: dict) -> dict:
    """Search for reference images matching the build request."""
    
    prompt = state.get("user_message", "")
    logger.info(f"[image_search] Searching images for: {prompt[:50]}...")

    reference_images = []

    if pplx_client:
        query = f"Provide a list of direct image URLs (ending in .jpg or .png) for: {prompt}"
        
        try:
            response = pplx_client.chat.completions.create(
                model="sonar-pro",
                messages=[{"role": "user", "content": query}]
            )

            content = response.choices[0].message.content
            reference_images = extract_image_urls(content)

        except Exception as e:
            logger.error(f"Perplexity Search Error: {e}")

    return {
        "reference_images": reference_images
    }