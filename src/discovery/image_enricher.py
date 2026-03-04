"""Enrich products with images by fetching og:image from product pages.

Tries multiple strategies to find product images:
1. og:image meta tag (most common)
2. twitter:image meta tag
3. JSON-LD Product schema image
4. Standard meta image tag
"""

import asyncio
import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

# Patterns to find images in HTML — tried in priority order
IMAGE_PATTERNS = [
    # og:image — property before content
    re.compile(
        r'<meta\s+[^>]*?property=["\']og:image["\'][^>]*?content=["\'](https?://[^"\']+)["\']',
        re.IGNORECASE,
    ),
    # og:image — content before property
    re.compile(
        r'<meta\s+[^>]*?content=["\'](https?://[^"\']+)["\'][^>]*?property=["\']og:image["\']',
        re.IGNORECASE,
    ),
    # twitter:image — name before content
    re.compile(
        r'<meta\s+[^>]*?(?:name|property)=["\']twitter:image["\'][^>]*?content=["\'](https?://[^"\']+)["\']',
        re.IGNORECASE,
    ),
    # twitter:image — content before name
    re.compile(
        r'<meta\s+[^>]*?content=["\'](https?://[^"\']+)["\'][^>]*?(?:name|property)=["\']twitter:image["\']',
        re.IGNORECASE,
    ),
    # Generic meta image
    re.compile(
        r'<meta\s+[^>]*?name=["\']image["\'][^>]*?content=["\'](https?://[^"\']+)["\']',
        re.IGNORECASE,
    ),
]

# JSON-LD product image pattern
JSONLD_PATTERN = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _extract_jsonld_image(html: str) -> str:
    """Try to extract product image from JSON-LD structured data."""
    for match in JSONLD_PATTERN.finditer(html):
        try:
            data = json.loads(match.group(1))
            # Handle @graph wrapper
            if isinstance(data, dict) and "@graph" in data:
                for item in data["@graph"]:
                    if isinstance(item, dict) and item.get("@type") in ("Product", "ClothingStore", "IndividualProduct"):
                        img = item.get("image")
                        if isinstance(img, str) and img.startswith("http"):
                            return img
                        if isinstance(img, list) and img:
                            return img[0] if isinstance(img[0], str) else img[0].get("url", "")
                        if isinstance(img, dict):
                            return img.get("url", "")
            # Direct Product type
            if isinstance(data, dict) and data.get("@type") in ("Product", "ClothingStore", "IndividualProduct"):
                img = data.get("image")
                if isinstance(img, str) and img.startswith("http"):
                    return img
                if isinstance(img, list) and img:
                    return img[0] if isinstance(img[0], str) else img[0].get("url", "")
                if isinstance(img, dict):
                    return img.get("url", "")
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue
    return ""


async def fetch_og_image(url: str, timeout: float = 10.0) -> str:
    """Fetch a product page and extract the product image.

    Tries multiple strategies: og:image, twitter:image, JSON-LD, meta image.

    Args:
        url: The product page URL.
        timeout: Request timeout in seconds.

    Returns:
        The image URL, or empty string if not found.
    """
    if not url:
        return ""

    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=timeout
        ) as client:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
            }
            resp = await client.get(url, headers=headers)

            if resp.status_code != 200:
                logger.debug(f"Got status {resp.status_code} from {url}")
                return ""

            # Check the first 100KB for meta tags and JSON-LD
            html = resp.text[:100000]

            # Try meta tag patterns first (fastest)
            for pattern in IMAGE_PATTERNS:
                match = pattern.search(html)
                if match:
                    img_url = match.group(1).strip()
                    if _is_valid_image_url(img_url):
                        return img_url

            # Try JSON-LD structured data
            jsonld_img = _extract_jsonld_image(html)
            if jsonld_img and _is_valid_image_url(jsonld_img):
                return jsonld_img

    except Exception as e:
        logger.debug(f"Failed to fetch image from {url}: {e}")

    return ""


def _is_valid_image_url(url: str) -> bool:
    """Check if an image URL looks valid and usable."""
    if not url or len(url) < 15:
        return False
    if url.startswith("data:"):
        return False
    if "placeholder" in url.lower() or "default" in url.lower():
        return False
    if not url.startswith("http"):
        return False
    # Must have a reasonable image extension or be a dynamic image URL
    return True


async def enrich_product_images(products: list) -> list:
    """Populate image URLs by fetching og:image from product pages.

    Fetches for ALL products because LLM-provided image URLs are often
    hallucinated or broken. Only skips if the product has no purchase_url.

    Args:
        products: List of Product objects (modified in-place).

    Returns:
        The same list with image URLs populated where possible.
    """
    tasks = []
    indices = []

    for i, p in enumerate(products):
        if p.purchase_url:
            tasks.append(fetch_og_image(p.purchase_url))
            indices.append(i)

    if not tasks:
        logger.info("No products with purchase URLs, skipping image enrichment")
        return products

    logger.info(f"Fetching images for {len(tasks)} products from their product pages...")

    # Run all fetches concurrently (they're I/O-bound)
    results = await asyncio.gather(*tasks, return_exceptions=True)

    enriched = 0
    kept_original = 0
    no_image = 0
    for idx, result in zip(indices, results):
        if isinstance(result, str) and result:
            products[idx].image_url = result
            enriched += 1
        elif products[idx].image_url and _is_valid_image_url(products[idx].image_url):
            # Keep the LLM-provided URL as fallback
            kept_original += 1
        else:
            products[idx].image_url = ""
            no_image += 1
            logger.debug(
                f"No image found for '{products[idx].product_name}' at {products[idx].purchase_url}"
            )

    logger.info(
        f"Image enrichment: {enriched} from og:image, {kept_original} kept original, "
        f"{no_image} still missing"
    )
    return products
