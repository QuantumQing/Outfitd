"""Perplexity Sonar API client — web search for real products."""

import logging
import httpx

from src.config import settings

logger = logging.getLogger(__name__)

PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"


async def search_products(query: str) -> str:
    """Search for men's clothing products using Perplexity Sonar API.

    Args:
        query: Natural language search query for products.

    Returns:
        Raw text response from Perplexity containing product information,
        with verified citation URLs appended.
    """
    headers = {
        "Authorization": f"Bearer {settings.perplexity_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "sonar",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a shopping assistant. Find real, specific products available for purchase online. "
                    "For each product found, provide: "
                    "product name, brand, category (top/bottom/outerwear/shoes/belt/accessory), "
                    "color, price (USD), retailer name, and the DIRECT URL to the specific product page "
                    "(NOT the brand homepage — the URL must go to the specific item's page where you can buy it, "
                    "e.g. nordstrom.com/s/item-name/12345 or jcrew.com/p/mens/shirts/AB123). "
                    "Also include the product image URL if available. "
                    "Only include products from retailers with 30+ day return policies. "
                    "Format each product clearly and separately."
                ),
            },
            {"role": "user", "content": query},
        ],
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(PERPLEXITY_URL, headers=headers, json=payload)
        response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]

    # Capture citations — these are REAL URLs that Perplexity actually visited
    citations = data.get("citations", [])
    if citations:
        logger.info(f"Perplexity returned {len(citations)} verified citation URLs")
        # Append citations to content so the product parser can use them
        citations_text = "\n\nVERIFIED SOURCE URLs (use these as purchase_url when they match a product):\n"
        for i, url in enumerate(citations, 1):
            citations_text += f"[{i}] {url}\n"
        content += citations_text

    logger.info(f"Perplexity search for '{query[:50]}...' returned {len(content)} chars")
    return content
