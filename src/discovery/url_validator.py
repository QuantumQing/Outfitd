"""Validate product URLs to ensure they point to specific product pages, not homepages."""

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def is_product_page_url(url: str) -> bool:
    """Check if a URL appears to be a specific product page, not a homepage.

    Returns True if the URL has a meaningful path that looks like a product page.
    Returns False for homepages, category-only pages, and invalid URLs.
    """
    if not url or not url.startswith("http"):
        return False

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    path = parsed.path.rstrip("/")

    # Reject if path is empty or just "/"
    if not path or path == "":
        return False

    # Split into segments and filter empties
    path_segments = [s for s in path.split("/") if s]

    # Must have at least 1 meaningful path segment
    if len(path_segments) < 1:
        return False

    # Reject very short paths (likely just "/en" or "/us")
    if len(path) < 5:
        return False

    # Reject paths that are only locale codes like /en, /us, /en-us
    if len(path_segments) == 1 and len(path_segments[0]) <= 5:
        # Likely a locale code like "en", "us", "en-us"
        return False

    return True


def validate_and_filter_products(products: list) -> list:
    """Filter out products that don't have valid product-page URLs.

    Args:
        products: List of Product objects.

    Returns:
        Filtered list with only products that have specific product page URLs.
    """
    valid = []
    rejected = 0

    for p in products:
        if is_product_page_url(p.purchase_url):
            valid.append(p)
        else:
            rejected += 1
            logger.warning(
                f"Rejected product '{p.product_name}' — URL is not a product page: {p.purchase_url}"
            )

    if rejected:
        logger.info(
            f"URL validation: kept {len(valid)}/{len(products)} products "
            f"({rejected} rejected for homepage/invalid URLs)"
        )

    return valid
