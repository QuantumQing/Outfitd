"""Shoe recommendations based on the latest trunk's outfit palette."""

import logging

from src.curation.llm_client import call_llm
from src.config import settings
from src.database import get_db
from src.discovery.serper import search_shopping

logger = logging.getLogger(__name__)

MAX_SHOES = 12


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


def _get_latest_trunk_id() -> int | None:
    """Get the ID of the latest generated trunk."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM trunk ORDER BY generated_at DESC LIMIT 1").fetchone()
        return row["id"] if row else None


def _get_trunk_palette(trunk_id: int) -> list[str]:
    """Extract dominant top/bottom colors from a given trunk."""
    with get_db() as conn:
        items = conn.execute(
            "SELECT color, category FROM trunk_item "
            "WHERE trunk_id = ? AND category IN ('top', 'bottom') AND color != ''",
            (trunk_id,),
        ).fetchall()

    colors = [i["color"] for i in items if i["color"]]
    # Deduplicate while preserving order
    seen = set()
    unique_colors = []
    for c in colors:
        cl = c.lower().strip()
        if cl not in seen:
            seen.add(cl)
            unique_colors.append(c)
    return unique_colors[:8]


async def _generate_shoe_queries(palette: list[str]) -> list[dict]:
    """Ask the LLM to generate 6-7 diverse shoe search queries with pairing justifications."""
    palette_str = ", ".join(palette) if palette else "navy, olive, white, charcoal"
    persona_doc = _get_user_persona()

    system_prompt = f"""You are a men's stylist expert in shoe-outfit coordination.
Given a palette of outfit colors from a client's wardrobe, recommend 6-7 DIVERSE shoe search queries.

CRITICAL RULES FOR SHOES:
1. YOU MUST NOT RECOMMEND ONLY DRESS SHOES OR LOAFERS.
2. ENFORCE VARIETY: You must explicitly generate queries for:
   - At least 2 pairs of Sneakers (e.g. low-top, knit, or canvas)
   - At least 2 pairs of Casual Boots (e.g. Chelsea, chukka)
   - At least 1 Athletic/Running shoe
   - At most 1 casual loafer
3. DO NOT recommend only brown. Mix up colors (white, black, grey, navy, tan, olive, etc.).
4. MUST ADHERE TO THE USER PERSONA BELOW. Note that the client wears casual clothing (tees, polos, jeans, shorts), so very formal dress shoes will look out of place.
5. Your queries must be specific enough to find actual products (Brand + Style + Color + "men").
6. Provide a specific 'pairing_note' for EACH shoe explaining exactly why it goes with the provided color palette or the client's casual/WFH persona.

**USER PERSONA:**
{persona_doc}

Return valid JSON matching this structure:
{{
  "queries": [
    {{"query": "Cole Haan white leather sneakers men", "pairing_note": "A crisp white sneaker provides clean contrast to the olive and navy in your casual outfits."}},
    {{"query": "Thursday Boot Co black chelsea boots men", "pairing_note": "A sleek black boot dresses up the dark jeans you prefer while maintaining an athletic edge."}}
  ]
}}"""

    user_prompt = f"""Outfit color palette from latest trunk: {palette_str}

Generate 6-7 completely different shoe search queries meeting the EXACT variety requirements (sneakers, boots, athletic) with pairing notes."""

    result = await call_llm(system_prompt, user_prompt, temperature=0.7, max_tokens=2048)

    if isinstance(result, dict) and "queries" in result:
        return result["queries"][:7]
    return [
         {"query": "white men's leather low-top sneakers", "pairing_note": "Classic white sneakers perfectly contrast your darker denim."},
         {"query": "black men's Chelsea boots leather", "pairing_note": "Sleek and versatile for dressing up your athletic-fit chinos."},
         {"query": "grey suede chukka boots men", "pairing_note": "A softer neutral that pairs effortlessly with olive and navy."},
         {"query": "navy canvas men's sneakers", "pairing_note": "Monochromatic pairing for dark indigo jeans."},
         {"query": "tan leather loafers men", "pairing_note": "A warm contrast for your smart-casual looks."}
    ]


_cached_shoes: list[dict] = []
_cached_trunk_id: int | None = None

async def generate_shoe_recommendations() -> list[dict]:
    """Generate shoe recommendations paired to the latest trunk's palette.
    Caches the results so the page loads instantly on subsequent visits
    for the same trunk.
    """
    global _cached_shoes, _cached_trunk_id
    trunk_id = _get_latest_trunk_id()

    if trunk_id is not None and _cached_trunk_id == trunk_id and _cached_shoes:
        logger.info("Returning cached shoe recommendations")
        return _cached_shoes

    if trunk_id is None:
        return []

    palette = _get_trunk_palette(trunk_id)
    palette_str = ", ".join(palette) if palette else "neutral tones"

    queries = await _generate_shoe_queries(palette)
    logger.info(f"Generated {len(queries)} shoe queries for palette: {palette_str}")

    seen_urls: set[str] = set()
    shoes: list[dict] = []

    for q in queries:
        if len(shoes) >= MAX_SHOES:
            break
        query_text = q.get("query", "")
        note = q.get("pairing_note", f"Pairs well with your {palette_str} outfits")
        if not query_text:
            continue
            
        results = await search_shopping(query_text, num_results=5)
        for product in results:
            if product.purchase_url in seen_urls:
                continue
            if product.category != "shoes":
                continue
            seen_urls.add(product.purchase_url)
            shoes.append({
                "product_name": product.product_name,
                "brand": product.brand,
                "color": product.color,
                "price": product.price,
                "retailer": product.retailer,
                "purchase_url": product.purchase_url,
                "image_url": product.image_url,
                "pairing_note": note,
            })
            if len(shoes) >= MAX_SHOES:
                break

    _cached_shoes = shoes
    _cached_trunk_id = trunk_id

    logger.info(f"Returning and caching {len(shoes)} shoe recommendations")
    return shoes
