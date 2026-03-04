"""Serper.dev Google Shopping API — structured product search with real URLs and images."""

import logging
from urllib.parse import urlparse

import httpx

from src.config import settings
from src.models import Product

logger = logging.getLogger(__name__)

SERPER_URL = "https://google.serper.dev/shopping"
SERPER_SEARCH_URL = "https://google.serper.dev/search"

BLOCKED_DOMAINS = frozenset({
    # Auction / resale marketplaces
    "ebay.com", "ebay.ca", "ebay.co.uk", "ebay.com.au",
    # Secondhand / thrift platforms
    "poshmark.com", "depop.com", "mercari.com", "thredup.com",
    "vestiairecollective.com", "vestiaire.com", "tradesy.com",
    "grailed.com", "heroine.com", "vinted.com", "swap.com",
    "therealreal.com", "zippychicks.com",
    # Discount / steep-sale aggregators that often list used goods
    "steepandcheap.com",
    # Big box department stores (to prefer direct D2C links)
    "dillards.com", "macys.com", "nordstrom.com", "bloomingdales.com",
    "saksfifthavenue.com", "neimanmarcus.com", "jcpenney.com", "kohls.com",
    "belk.com", "walmart.com", "target.com", "etsy.com", "nordstromrack.com",
    "outlet46.com", "outlet46.de", "modesens.com",
})

# URL path segments that indicate a women's section of a retailer
_WOMENS_PATH_SEGMENTS = frozenset({
    "/women", "/womens", "/women-", "/she/", "/her/",
    "/ladies", "/female", "/womenswear",
})

# Product title keywords that strongly indicate women's clothing
_WOMENS_TITLE_KEYWORDS = [
    "women's", "womens", "ladies", "for women", "womenswear",
    "girl's", "girls'", "feminine",
]


def _is_womens_product(title: str, url: str) -> bool:
    """Return True if the product appears to be women's clothing."""
    t = title.lower()
    if any(kw in t for kw in _WOMENS_TITLE_KEYWORDS):
        return True
    url_lower = url.lower()
    if any(seg in url_lower for seg in _WOMENS_PATH_SEGMENTS):
        return True
    return False


async def search_google(query: str, num_results: int = 10) -> list[dict]:
    """Perform a standard Google Search via Serper.dev API."""
    headers = {
        "X-API-KEY": settings.serper_api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "q": query,
        "num": num_results,
        "gl": "us",
        "hl": "en",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(SERPER_SEARCH_URL, headers=headers, json=payload)
        response.raise_for_status()

    data = response.json()
    return data.get("organic", [])


# Color keywords sorted longest-first so "navy blue" matches before "blue"
_COLOR_KEYWORDS = sorted([
    "navy blue", "navy", "royal blue", "cobalt", "slate blue", "light blue", "sky blue", "blue",
    "olive green", "olive", "forest green", "dark green", "army green", "hunter green", "sage", "green",
    "dark brown", "cognac", "brown", "rust", "camel", "khaki", "beige", "cream", "tan",
    "heather grey", "light grey", "light gray", "charcoal", "slate", "heather gray", "grey", "gray",
    "off white", "white", "ivory", "ecru", "oatmeal",
    "black",
    "burgundy", "maroon", "wine", "crimson", "red", "rose", "pink",
    "mustard", "yellow", "orange", "copper",
    "lavender", "violet", "purple",
    "stone", "sand", "chambray", "indigo", "denim", "teal", "turquoise",
    "cedar", "amber",
], key=len, reverse=True)


def _extract_color_from_text(text: str) -> str:
    """Extract the first recognisable color keyword from a product title or query."""
    t = text.lower()
    for color in _COLOR_KEYWORDS:
        if color in t:
            return color.title()
    return ""


def _classify_product(title: str) -> tuple[str, str]:
    """Classify a product into (category, formality_tier) based on its title.

    formality_tier: 'athletic' | 'casual' | 'smart_casual' | 'formal' | ''
    """
    title_lower = title.lower()

    # ── Athletic bottoms (check before generic bottom keywords) ──────────────
    athletic_bottom_kw = [
        "jogger", "sweatpant", "athletic short", "workout short", "gym short",
        "running short", "track pant", "board short", "swim trunk",
    ]
    if any(kw in title_lower for kw in athletic_bottom_kw):
        return ("bottom", "athletic")

    # ── Smart-casual bottoms ──────────────────────────────────────────────────
    smart_bottom_kw = ["trouser", "dress pant", "slacks", "flat-front pant"]
    if any(kw in title_lower for kw in smart_bottom_kw):
        return ("bottom", "smart_casual")

    # ── Smart-casual tops ─────────────────────────────────────────────────────
    smart_top_kw = ["oxford shirt", "polo", "button-down", "button down", "flannel shirt", "poplin"]
    if any(kw in title_lower for kw in smart_top_kw):
        return ("top", "smart_casual")

    # ── Athletic tops ─────────────────────────────────────────────────────────
    athletic_top_kw = ["dri-fit", "dry-fit", "moisture-wick", "performance tee"]
    if any(kw in title_lower for kw in athletic_top_kw):
        return ("top", "athletic")

    # ── Outerwear (blazer = smart_casual; other jackets = casual) ────────────
    if "blazer" in title_lower:
        return ("outerwear", "smart_casual")
    outer_keywords = [
        "jacket", "coat", "parka", "windbreaker", "bomber",
        "anorak", "overcoat", "peacoat", "puffer", "down vest",
        "outerwear", "rain",
    ]
    if any(kw in title_lower for kw in outer_keywords):
        return ("outerwear", "casual")

    # ── Generic tops ─────────────────────────────────────────────────────────
    top_keywords = [
        "shirt", "tee", "t-shirt", "henley", "sweater", "pullover",
        "hoodie", "sweatshirt", "blouse", "top", "tank", "vest", "cardigan",
        "jersey", "short sleeve", "shortsleeve", "long sleeve", "longsleeve",
        "crewneck", "v-neck", "flannel",
    ]
    if any(kw in title_lower for kw in top_keywords):
        return ("top", "casual")

    # ── Generic bottoms ───────────────────────────────────────────────────────
    bottom_keywords = [
        "pant", "chino", "jean", "denim", "shorts",
        "boardshort", "cargo", "khaki",
    ]
    if any(kw in title_lower for kw in bottom_keywords):
        return ("bottom", "casual")

    # ── Shoes ─────────────────────────────────────────────────────────────────
    shoe_keywords = [
        "shoe", "boot", "sneaker", "loafer", "oxford", "derby",
        "sandal", "slipper", "trainer", "footwear", "moccasin",
        "chelsea", "chukka",
    ]
    if any(kw in title_lower for kw in shoe_keywords):
        return ("shoes", "")

    # ── Belt ─────────────────────────────────────────────────────────────────
    if "belt" in title_lower:
        return ("belt", "")

    # ── Accessory fallback ────────────────────────────────────────────────────
    accessory_keywords = [
        "watch", "sunglasses", "wallet", "hat", "cap", "scarf",
        "tie", "socks", "bag", "backpack", "bracelet", "gloves",
    ]
    if any(kw in title_lower for kw in accessory_keywords):
        return ("accessory", "")

    return ("top", "")  # default


def _classify_category(title: str) -> str:
    """Backward-compat wrapper — returns only the category string."""
    return _classify_product(title)[0]


def _parse_price(price_str: str) -> float:
    """Parse price string like '$79.50' to float."""
    if not price_str:
        return 0.0
    try:
        cleaned = price_str.replace("$", "").replace(",", "").strip()
        # Handle range like "$49.99 - $79.99" — take the first
        if "-" in cleaned or "–" in cleaned:
            cleaned = cleaned.split("-")[0].split("–")[0].strip()
        return float(cleaned)
    except (ValueError, IndexError):
        return 0.0


def _extract_brand(source: str, title: str) -> str:
    """Extract brand from source or title."""
    # Serper 'source' is usually the retailer, not the brand
    # Try to extract brand from the title (usually first word(s) before product type)
    if source:
        return source
    return ""


async def search_shopping(query: str, num_results: int = 10) -> list[Product]:
    """Search Google Shopping via Serper.dev API.

    Args:
        query: Search query string.
        num_results: Number of results to return.

    Returns:
        List of Product objects with real names, URLs, images, and prices.
    """
    headers = {
        "X-API-KEY": settings.serper_api_key,
        "Content-Type": "application/json",
    }

    payload = {
        "q": query,
        "num": num_results,
        "gl": "us",  # US results
        "hl": "en",  # English
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(SERPER_URL, headers=headers, json=payload)
        response.raise_for_status()

    data = response.json()
    shopping_results = data.get("shopping", [])

    if not shopping_results:
        logger.warning(f"No shopping results for: {query}")
        return []

    products = []
    seen_urls = set()
    brand_counts: dict[str, int] = {}  # cap per-brand to 2 results per query

    for item in shopping_results:
        title = item.get("title", "")
        link = item.get("link", "")
        image_url = item.get("imageUrl", "")
        price_str = item.get("price", "")
        source = item.get("source", "")

        # Skip if no link or duplicate
        if not link or link in seen_urls:
            continue
        seen_urls.add(link)

        # Verify it's a real product page URL (not a homepage)
        parsed = urlparse(link)
        # Check if path is too short AND query is empty/short
        if len(parsed.path.rstrip("/")) < 2 and len(parsed.query) < 5:
            logger.debug(f"Skipping homepage-like URL: {link}")
            continue

        # Block resale / auction marketplaces by URL domain AND source name
        parsed_domain = parsed.netloc.lower().removeprefix("www.")
        if any(parsed_domain == bd or parsed_domain.endswith("." + bd) for bd in BLOCKED_DOMAINS):
            logger.debug(f"Blocked domain: {parsed_domain}")
            continue
        source_lower = source.lower()
        if any(bd.split(".")[0] in source_lower for bd in BLOCKED_DOMAINS):
            logger.debug(f"Blocked source: {source}")
            continue

        # Block foreign TLDs to avoid international merchants
        foreign_tlds = ('.de', '.uk', '.it', '.fr', '.nl', '.es', '.au', '.eu', '.ch', '.se')
        if parsed_domain.endswith(foreign_tlds):
            logger.debug(f"Blocked foreign TLD: {parsed_domain}")
            continue

        # Skip women's products
        if _is_womens_product(title, link):
            logger.debug(f"Skipping women's product: {title[:60]}")
            continue

        # Per-brand cap: at most 2 results per brand per query
        brand_key = source.lower().strip()
        if brand_key and brand_counts.get(brand_key, 0) >= 2:
            logger.debug(f"Brand cap hit for '{source}' — skipping")
            continue

        # Classify category and formality tier from title
        category, formality_tier = _classify_product(title)

        product = Product(
            product_name=title,
            brand=source,
            category=category,
            formality_tier=formality_tier,
            color=_extract_color_from_text(title),
            price=_parse_price(price_str),
            retailer=source,
            purchase_url=link,
            image_url=image_url,
            return_policy_days=30,
        )
        products.append(product)
        if brand_key:
            brand_counts[brand_key] = brand_counts.get(brand_key, 0) + 1

    logger.info(
        f"Serper shopping: '{query[:50]}...' → {len(products)} products "
        f"(from {len(shopping_results)} results)"
    )
    return products


async def search_products_via_shopping(
    queries: list, target_count: int = 25
) -> list[Product]:
    """Run multiple Google Shopping searches and deduplicate results.

    Args:
        queries: List of SearchQuery objects with .query and .target_category.
        target_count: Approximate target number of unique products.

    Returns:
        Deduplicated list of Product objects.
    """
    import asyncio

    all_products = []
    seen_urls = set()

    # Run searches in batches to avoid rate limits
    batch_size = 3
    for i in range(0, len(queries), batch_size):
        batch = queries[i:i + batch_size]
        tasks = [search_shopping(q.query, num_results=10) for q in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for j, result in enumerate(results):
            if isinstance(result, list):
                query_obj = batch[j]
                for product in result:
                    if product.purchase_url not in seen_urls:
                        seen_urls.add(product.purchase_url)
                        # Override category if the search query had a target
                        if query_obj.target_category and not product.category:
                            product.category = query_obj.target_category
                        # Do NOT fall back to query color — the returned product may
                        # be a different color than the query's target. Title-only
                        # color is more accurate; unknown color renders as a neutral.
                        all_products.append(product)
            elif isinstance(result, Exception):
                logger.warning(f"Shopping search failed: {result}")

        # Brief pause between batches
        if i + batch_size < len(queries):
            await asyncio.sleep(0.3)

    logger.info(
        f"Google Shopping discovery: {len(all_products)} unique products "
        f"from {len(queries)} queries"
    )
    return all_products
