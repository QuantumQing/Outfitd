#!/usr/bin/env python3
"""Repair trunk items: find real product page URLs and images.

Zero API cost — uses direct HTTP requests to retailer sites.
Strategies:
1. Try Shopify-style /products/{slug} URL construction
2. Try retailer search pages to find product links
3. Fetch og:image from found product pages
"""

import asyncio
import json
import re
import sqlite3
import logging
from urllib.parse import quote_plus, urlparse

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

DB_PATH = "/app/data/trunk.db"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

# Map brand/retailer names to their domains
BRAND_DOMAINS = {
    "everlane": "everlane.com",
    "j.crew": "jcrew.com",
    "jcrew": "jcrew.com",
    "j crew": "jcrew.com",
    "levi's": "levi.com",
    "levis": "levi.com",
    "levi": "levi.com",
    "thursday boot co": "thursdayboots.com",
    "thursday boots": "thursdayboots.com",
    "uniqlo": "uniqlo.com",
    "allbirds": "allbirds.com",
    "vuori": "vuori.com",
    "vuori clothing": "vuori.com",
    "bonobos": "bonobos.com",
    "nordstrom": "nordstrom.com",
    "nike": "nike.com",
    "adidas": "adidas.com",
    "patagonia": "patagonia.com",
    "todd snyder": "toddsnyder.com",
    "buck mason": "buckmason.com",
    "taylor stitch": "taylorstitch.com",
    "faherty": "faherty.com",
    "rhone": "rhone.com",
    "banana republic": "bananarepublic.gap.com",
    "gap": "gap.com",
    "madewell": "madewell.com",
    "brooks brothers": "brooksbrothers.com",
    "cuts clothing": "cutsclothing.com",
    "abercrombie & fitch": "abercrombie.com",
    "abercrombie": "abercrombie.com",
    "h&m": "hm.com",
    "zara": "zara.com",
}

# og:image extraction patterns
OG_IMAGE_PATTERNS = [
    re.compile(
        r'<meta\s+[^>]*?property=["\']og:image["\'][^>]*?content=["\'](https?://[^"\']+)["\']',
        re.IGNORECASE,
    ),
    re.compile(
        r'<meta\s+[^>]*?content=["\'](https?://[^"\']+)["\'][^>]*?property=["\']og:image["\']',
        re.IGNORECASE,
    ),
    re.compile(
        r'<meta\s+[^>]*?(?:name|property)=["\']twitter:image["\'][^>]*?content=["\'](https?://[^"\']+)["\']',
        re.IGNORECASE,
    ),
    re.compile(
        r'<meta\s+[^>]*?content=["\'](https?://[^"\']+)["\'][^>]*?(?:name|property)=["\']twitter:image["\']',
        re.IGNORECASE,
    ),
]

JSONLD_PATTERN = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def get_domain(brand: str, retailer: str, current_url: str) -> str:
    """Get the domain for a brand/retailer."""
    for name in [brand.lower().strip(), retailer.lower().strip()]:
        if name in BRAND_DOMAINS:
            return BRAND_DOMAINS[name]
    # Extract from existing URL
    try:
        parsed = urlparse(current_url)
        return parsed.netloc.replace("www.", "")
    except Exception:
        return ""


def slugify(name: str) -> str:
    """Convert product name to URL slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug


def slugify_base(name: str) -> str:
    """Convert product name to URL slug, stripping color/variant suffixes."""
    cleaned = re.sub(r"\s*[-–]\s*\w+(\s+\w+)?$", "", name)
    cleaned = re.sub(r"\s+in\s+\w+(\s+\w+)*$", "", cleaned, flags=re.IGNORECASE)
    slug = re.sub(r"[^a-z0-9]+", "-", cleaned.lower()).strip("-")
    return slug


def slugify_with_brand(brand: str, name: str) -> str:
    """Slug with brand prefix (some retailer URLs include brand)."""
    combined = f"{brand} {name}"
    return re.sub(r"[^a-z0-9]+", "-", combined.lower()).strip("-")


async def try_url_exists(client: httpx.AsyncClient, url: str) -> str | None:
    """Check if a URL exists and isn't a redirect to homepage."""
    try:
        resp = await client.get(url, headers=HEADERS, follow_redirects=True)
        if resp.status_code == 200:
            final_url = str(resp.url)
            path = urlparse(final_url).path.rstrip("/")
            # Make sure we didn't redirect to homepage
            if len(path) > 5:
                return final_url
    except Exception:
        pass
    return None


def extract_image_from_html(html: str) -> str:
    """Extract product image from HTML using multiple strategies."""
    # Try meta tag patterns
    for pattern in OG_IMAGE_PATTERNS:
        match = pattern.search(html)
        if match:
            img_url = match.group(1).strip()
            if img_url.startswith("http") and len(img_url) > 15:
                if "placeholder" not in img_url.lower():
                    return img_url

    # Try JSON-LD structured data
    for match in JSONLD_PATTERN.finditer(html):
        try:
            data = json.loads(match.group(1))
            img = _extract_image_from_jsonld(data)
            if img:
                return img
        except (json.JSONDecodeError, TypeError):
            continue

    return ""


def _extract_image_from_jsonld(data) -> str:
    """Recursively extract image from JSON-LD data."""
    if isinstance(data, list):
        for item in data:
            result = _extract_image_from_jsonld(item)
            if result:
                return result
        return ""

    if not isinstance(data, dict):
        return ""

    dtype = data.get("@type", "")
    if isinstance(dtype, list):
        is_product = any(t in ("Product", "IndividualProduct") for t in dtype)
    else:
        is_product = dtype in ("Product", "IndividualProduct")

    if is_product:
        img = data.get("image")
        if isinstance(img, str) and img.startswith("http"):
            return img
        if isinstance(img, list) and img:
            first = img[0]
            return first if isinstance(first, str) else first.get("url", "")
        if isinstance(img, dict):
            return img.get("url", img.get("contentUrl", ""))

    # Check @graph
    for item in data.get("@graph", []):
        result = _extract_image_from_jsonld(item)
        if result:
            return result

    return ""


async def find_product_url_and_image(
    client: httpx.AsyncClient,
    brand: str,
    product_name: str,
    retailer: str,
    current_url: str,
) -> tuple[str, str]:
    """Find the real product page URL and image.

    Returns (product_url, image_url).
    """
    domain = get_domain(brand, retailer, current_url)
    if not domain:
        logger.warning(f"  Could not determine domain for {brand}/{retailer}")
        return current_url, ""

    # Generate slug variations to try
    slug_variations = list(dict.fromkeys([  # deduplicate while preserving order
        slugify_base(product_name),
        slugify(product_name),
        slugify_with_brand(brand, product_name),
        # Try with "mens" prefix
        "mens-" + slugify_base(product_name),
        "men-" + slugify_base(product_name),
    ]))

    # Strategy 1: Try direct product URL construction
    url_prefixes = [f"https://www.{domain}", f"https://{domain}"]
    path_patterns = ["/products/{slug}", "/p/{slug}"]

    for slug in slug_variations:
        for prefix in url_prefixes:
            for pattern in path_patterns:
                url = prefix + pattern.format(slug=slug)
                result = await try_url_exists(client, url)
                if result:
                    logger.info(f"  ✓ Found via URL construction: {result}")
                    # Fetch the page for og:image
                    image = await _fetch_image_from_url(client, result)
                    return result, image

    # Strategy 2: Try retailer's search page
    search_terms = slugify_base(product_name).replace("-", " ")
    search_paths = [
        f"/search?q={quote_plus(search_terms)}",
        f"/search?type=product&q={quote_plus(search_terms)}",
        f"/search?q={quote_plus(product_name)}",
    ]

    for prefix in url_prefixes:
        for search_path in search_paths:
            try:
                search_url = prefix + search_path
                resp = await client.get(
                    search_url, headers=HEADERS, follow_redirects=True, timeout=12.0
                )
                if resp.status_code != 200:
                    continue

                html = resp.text[:80000]

                # Find product links in search results
                product_links = re.findall(
                    r'href="(/products/[^"?#]+)"', html
                )
                if not product_links:
                    product_links = re.findall(
                        r'href="(/p/[^"?#]+)"', html
                    )

                if product_links:
                    # Take the first result
                    product_url = prefix + product_links[0]
                    logger.info(f"  ✓ Found via site search: {product_url}")
                    image = await _fetch_image_from_url(client, product_url)
                    return product_url, image

            except Exception as e:
                logger.debug(f"  Search attempt failed: {e}")
                continue

    # Strategy 3: Try fetching even the homepage for og:image (last resort)
    logger.warning(f"  ✗ Could not find product page for {brand} {product_name}")

    # At least try to get the homepage og:image (better than nothing for brand)
    for prefix in url_prefixes:
        image = await _fetch_image_from_url(client, prefix)
        if image:
            return current_url, image

    return current_url, ""


async def _fetch_image_from_url(client: httpx.AsyncClient, url: str) -> str:
    """Fetch a URL and extract the product image."""
    try:
        resp = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=12.0)
        if resp.status_code == 200:
            return extract_image_from_html(resp.text[:100000])
    except Exception as e:
        logger.debug(f"  Image fetch failed from {url}: {e}")
    return ""


async def repair():
    """Main repair function."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get the latest trunk
    trunk = conn.execute(
        "SELECT id FROM trunk ORDER BY generated_at DESC LIMIT 1"
    ).fetchone()
    if not trunk:
        logger.error("No trunk found in database")
        return

    trunk_id = trunk["id"]
    items = conn.execute(
        "SELECT * FROM trunk_item WHERE trunk_id = ? ORDER BY id",
        (trunk_id,),
    ).fetchall()

    logger.info(f"Repairing {len(items)} items in trunk #{trunk_id}...")

    async with httpx.AsyncClient(timeout=15.0) as client:
        updated = 0
        for item in items:
            item_id = item["id"]
            product_name = item["product_name"]
            brand = item["brand"]
            retailer = item["retailer"]
            current_url = item["purchase_url"] or ""
            current_image = item["image_url"] or ""

            logger.info(f"\n→ [{item_id}] {brand} - {product_name}")
            logger.info(f"  Current URL: {current_url}")
            logger.info(f"  Current image: {current_image[:80] if current_image else 'NONE'}")

            new_url, new_image = await find_product_url_and_image(
                client, brand, product_name, retailer, current_url
            )

            # If we didn't find a new image, keep the old one
            if not new_image and current_image:
                new_image = current_image

            # Update if anything changed
            if new_url != current_url or new_image != current_image:
                conn.execute(
                    "UPDATE trunk_item SET purchase_url = ?, image_url = ? WHERE id = ?",
                    (new_url, new_image, item_id),
                )
                updated += 1
                url_status = "FIXED" if new_url != current_url else "same"
                img_status = "FIXED" if new_image != current_image else "same"
                logger.info(f"  ✓ Updated — url: {url_status}, image: {img_status}")
                if new_url != current_url:
                    logger.info(f"    New URL: {new_url}")
                if new_image != current_image:
                    logger.info(f"    New image: {new_image[:80]}")
            else:
                logger.info(f"  — No improvements found")

            # Be polite — slight delay between requests
            await asyncio.sleep(0.5)

    conn.commit()
    conn.close()
    logger.info(f"\n{'='*60}")
    logger.info(f"Done! Updated {updated}/{len(items)} items.")
    logger.info(f"Refresh the trunk page to see the changes.")


if __name__ == "__main__":
    asyncio.run(repair())
