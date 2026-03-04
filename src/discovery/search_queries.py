"""Phase 2 — LLM generates targeted search queries from the stylist brief."""

import logging

from src.curation.llm_client import call_llm
from src.config import settings
from src.models import SearchQuery, SearchQueriesResponse

logger = logging.getLogger(__name__)

def _get_user_persona() -> str:
    """Read the external user_persona.md for fine-tuning rules."""
    try:
        import pathlib
        root_dir = pathlib.Path(__file__).parent.parent.parent
        with open(root_dir / "user_persona.md", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.warning(f"Could not read user_persona.md: {e}")
        return ""


def _bottom_distribution_rule(occasion: str) -> str:
    """Return LLM instruction for bottom query distribution based on occasion."""
    occ = occasion.lower()
    if occ == "casual":
        return "60% jeans (3 queries), 30% chinos (1-2 queries), 10% other casual pants (1 query)"
    elif "smart" in occ:
        return "40% chinos (2 queries), 40% dark jeans (2 queries), 20% dress trousers (1 query)"
    elif "athleisure" in occ or "athletic" in occ:
        return "50% joggers/athletic pants (2-3 queries), 30% shorts (1-2 queries), 20% chinos (1 query)"
    return "mix of jeans (2 queries), chinos (2 queries), other (1 query)"


async def generate_search_queries(
    stylist_brief: str,
    discovered_brands: list[str] = None,
    occasion: str = "casual",
    bottom_fit: str = "slim",
    bottom_rise: str = "low",
) -> list[SearchQuery]:
    """Generate 15-20 search queries from the stylist brief.

    Includes regular queries for needed wardrobe slots plus 2-3 wildcard
    queries that intentionally break from stated preferences.
    """
    bottom_rule = _bottom_distribution_rule(occasion)
    bottom_spec = f"{bottom_fit} fit, {bottom_rise}-rise"

    system_prompt = f"""You are an expert men's personal stylist generating product search queries.

Generate 15-20 search queries to find real men's clothing products online.
Each query should be specific enough to find actual products with prices and buy links.

Requirements:
- CRITICAL: Include at least 5-6 queries for base-layer TOPS (t-shirts, polos, button-downs, henleys). Every outfit needs a top.
- BOTTOMS: Include 5-7 queries with this distribution: {bottom_rule}
  BOTTOM FIT/RISE: The client wears {bottom_spec}. Include "{bottom_fit}" and "{bottom_rise}-rise" (or "low rise" / "mid rise") in every bottom query where it makes sense (e.g. "Levi's 511 slim fit low rise jeans men").
- OUTERWEAR: Include 1-2 queries (jackets, sweaters, blazers) — optional layers only, NOT substitutes for tops.
- BELTS: AT MOST 1 belt query. Skip if uncertain about fit.
- SHOES: Do NOT generate shoe queries — shoes are handled on a separate /shoes page.
- ACCESSORIES: 1-2 queries max (watch, wallet, hat).
- DEALBREAKERS: The brief contains specific styling dislikes. DO NOT generate ANY queries that include or relate to these (e.g., if 'long sleeves' is disliked, do not search for 'long sleeve shirt' or 'henley').
- Queries must be season-appropriate.
- Prioritize 'New Brand Discoveries' mentioned in the brief.
- BRAND DIVERSITY: Each brand should appear in AT MOST 2 queries. Spread queries across 6+ different brands. Never let one brand dominate.
- Keep queries focused on Brand + Product Type + Color + Gender.
- Vary colors (Navy, Olive, Charcoal, White, Maroon, Tan, Burgundy). Do NOT default to just Black/Grey.
- Avoid specific price ranges or sizes in the query — they filter results to zero.

Return JSON:
{{
  "queries": [
    {{"query": "J.Crew oxford shirt navy men", "target_category": "top", "is_wildcard": false}},
    {{"query": "Levi's 511 slim jeans dark indigo men", "target_category": "bottom", "is_wildcard": false}}
  ]
}}"""

    discovery_context = ""
    if discovered_brands:
        discovery_context = (
            f"\n**NEW BRAND DISCOVERIES:** {', '.join(discovered_brands)}\n"
            f"IMPORTANT: You MUST generate at least 3-4 queries specifically for these brands "
            f"to help the client discover them."
        )

    user_prompt = f"""Based on this stylist brief, generate search queries:

{stylist_brief}
{discovery_context}

**CRITICAL RULES OVERRIDE (USER PERSONA DOCUMENT):**
{_get_user_persona()}

Generate 15-20 queries (including 2-3 wildcard queries). ENSURE your generated queries strictly respect the exclusions and brand preferences established in the USER PERSONA DOCUMENT."""

    result = await call_llm(system_prompt, user_prompt, temperature=0.8, model=settings.openrouter_fast_model)

    queries = []
    if isinstance(result, dict) and "queries" in result:
        for q in result["queries"]:
            queries.append(SearchQuery(
                query=q.get("query", ""),
                target_category=q.get("target_category", ""),
                is_wildcard=q.get("is_wildcard", False),
            ))

    logger.info(f"Generated {len(queries)} search queries ({sum(1 for q in queries if q.is_wildcard)} wildcard)")
    return queries
