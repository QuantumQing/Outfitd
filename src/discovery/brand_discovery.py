"""Phase 1.5 — Discover new brands similar to user preferences."""

import logging
from src.curation.llm_client import call_llm
from src.config import settings
from src.database import get_db
from src.discovery.perplexity import search_products

logger = logging.getLogger(__name__)


async def discover_new_brands(liked_brands: list[str] = None) -> list[str]:
    """Find 5-10 brands similar to the user's preferences.

    Uses style_learning weights (from purchase/keep feedback) as the primary
    source. Falls back to liked_brands parameter only when no learning data exists.

    Returns:
        List of NEW brand names to explore.
    """
    # 1. Check style_learning for brand weights
    source_brands: list[str] = []
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT value FROM style_learning "
                "WHERE dimension = 'brand' AND weight > 0 "
                "ORDER BY weight DESC LIMIT 5"
            ).fetchall()
            source_brands = [r["value"] for r in rows]
    except Exception as e:
        logger.warning(f"Could not read style_learning for brands: {e}")

    # 2. Fall back to explicitly liked brands if no learning data
    if not source_brands and liked_brands:
        source_brands = liked_brands[:5]

    if not source_brands:
        brands_str = "J.Crew, Vuori, Bonobos"
    else:
        brands_str = ", ".join(source_brands[:5])

    perplexity_query = (
        f"What are 8-10 men's clothing brands similar to {brands_str}? "
        "List direct-to-consumer, heritage, and trending brands in 2026. Return brand names only."
    )
    logger.info(f"Querying Perplexity for new brands similar to: {brands_str}")

    # 1. Use Perplexity Sonar for real-time web brand discovery
    perplexity_response = await search_products(perplexity_query)

    if not perplexity_response:
        logger.warning("No brand discovery results from Perplexity.")
        return []

    # 2. Use Claude Haiku to extract brand names from Perplexity's response
    system_prompt = """You are a fashion brand expert.
Extract 5-8 distinct men's clothing brand names from the provided text.

Focus on:
- Direct-to-consumer brands (e.g. Buck Mason, Taylor Stitch, etc.)
- Heritage brands
- Trendy/up-and-coming brands for 2026

Return JSON: {"brands": ["Brand A", "Brand B", ...]}"""

    user_prompt = f"""User's known/liked brands: {', '.join(source_brands) if source_brands else 'None'}

Brand discovery text:
{perplexity_response[:2000]}

Extract 5-8 distinct brand names that are NOT in the user's known list.
Only return the names."""

    extract_result = await call_llm(system_prompt, user_prompt, temperature=0.5, model=settings.openrouter_fast_model)

    try:
        if isinstance(extract_result, dict) and "brands" in extract_result:
            discovered = extract_result["brands"]
            # Double check against source brands (case-insensitive)
            source_lower = {b.lower() for b in source_brands}
            final_brands = [b for b in discovered if b.lower() not in source_lower]
            logger.info(f"Discovered {len(final_brands)} new brands: {final_brands}")
            return final_brands
    except Exception as e:
        logger.error(f"Failed to extract brands: {e}")

    return []
