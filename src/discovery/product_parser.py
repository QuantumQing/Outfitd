"""Parse raw Perplexity search results into structured Product objects."""

import logging

from src.curation.llm_client import call_llm
from src.models import Product

logger = logging.getLogger(__name__)


async def parse_products(raw_results: list[str], target_categories: list[str] = None) -> list[Product]:
    """Use LLM to parse raw Perplexity text into structured Product objects.

    Args:
        raw_results: List of raw text responses from Perplexity searches.
        target_categories: Optional list of expected categories for context.

    Returns:
        List of parsed Product objects with validated fields.
    """
    # Combine all raw results
    combined = "\n\n---\n\n".join(raw_results)

    if not combined.strip():
        return []

    system_prompt = """You are a data extraction assistant. Extract product information from 
search results into structured JSON.

For each product found, extract:
- product_name: Full product name
- brand: Brand name
- category: One of: top, bottom, outerwear, shoes, belt, accessory
- color: Primary color
- price: Price as a number (USD)
- retailer: Store/retailer name
- purchase_url: DIRECT URL to the specific product page (see rules below)
- image_url: Product image URL if available (keep exact URL from source)  
- return_policy_days: Return window in days (default 30 if not specified)

CRITICAL URL RULES:
1. At the end of the search results you may see "VERIFIED SOURCE URLs" — these are REAL URLs 
   confirmed by the search engine. ALWAYS prefer these over any URLs mentioned in the text.
2. Match each product to its corresponding verified source URL based on the domain and content.
3. purchase_url MUST be a direct link to the specific product's page on the retailer's website.
4. VALID URL examples: 
   - "https://www.everlane.com/products/mens-organic-cotton-crew-tee"
   - "https://www.jcrew.com/p/mens/shirts/AE123"
   - "https://www.nordstrom.com/s/nike-air-max/6543210"
   - "https://thursdayboots.com/products/mens-captain-boot-brown"
5. INVALID URL examples (these are HOMEPAGES, NOT product pages):
   - "https://www.everlane.com/"
   - "https://www.jcrew.com"
   - "https://www.nike.com/"
6. If you cannot find a direct product page URL for an item, SKIP that product entirely.
   Do NOT use a homepage URL as a fallback.
- Deduplicate products that appear in multiple searches

Return JSON: {"products": [{...}, {...}]}"""

    user_prompt = f"""Extract all products from these search results:

{combined}

Return a JSON array of products."""

    result = await call_llm(system_prompt, user_prompt, temperature=0.2, max_tokens=8192)

    products = []
    
    if not isinstance(result, dict) or "products" not in result:
        logger.error(f"Failed to parse products. Expected dict with 'products' but got {type(result)}. Content: {str(result)[:500]}")

    if isinstance(result, dict) and "products" in result:
        for p in result["products"]:
            try:
                products.append(Product(
                    product_name=p.get("product_name", "Unknown"),
                    brand=p.get("brand", ""),
                    category=p.get("category", ""),
                    color=p.get("color", ""),
                    price=float(p.get("price", 0)),
                    retailer=p.get("retailer", ""),
                    purchase_url=p.get("purchase_url", ""),
                    image_url=p.get("image_url", ""),
                    return_policy_days=int(p.get("return_policy_days", 30)),
                ))
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping malformed product: {e}")

    logger.info(f"Parsed {len(products)} products from {len(raw_results)} search results")
    return products
