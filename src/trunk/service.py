"""Trunk generation orchestrator — chains discovery → curation → DB persistence."""

import json
import logging
import asyncio
from datetime import datetime

from src.database import get_db
from src.profile.service import get_profile
from src.curation.stylist_brief import generate_stylist_brief, _get_current_season
from src.discovery.search_queries import generate_search_queries
from src.discovery.serper import search_products_via_shopping
from src.curation.outfit_assembler import assemble_outfits
from src.models import TrunkResponse, TrunkItemResponse, FeedbackPayload

logger = logging.getLogger(__name__)


async def generate_trunk() -> TrunkResponse:
    profile = get_profile()
    season = _get_current_season()

    # Phase 1 — Stylist Brief
    logger.info("Phase 1: Generating stylist brief...")
    brief = await generate_stylist_brief(profile)
    logger.info(f"Stylist brief: {brief[:100]}...")

    # Phase 1.5 - Brand Discovery
    logger.info("Phase 1.5: Discovering new brands...")
    # Import inside function to avoid circular imports if any, though likely safe at top
    from src.discovery.brand_discovery import discover_new_brands
    discovered_brands = await discover_new_brands()
    logger.info(f"Discovered brands: {discovered_brands}")

    # Phase 2 — Search Queries
    logger.info("Phase 2: Generating search queries...")
    queries = await generate_search_queries(
        brief, discovered_brands,
        occasion=profile.occasion,
        bottom_fit=profile.bottom_fit,
        bottom_rise=profile.bottom_rise,
    )
    logger.info(f"Generated {len(queries)} queries")

    # Phase 3 — Product Discovery via Google Shopping
    logger.info("Phase 3: Searching Google Shopping for products...")
    products = await search_products_via_shopping(queries)
    logger.info(f"Discovered {len(products)} products from Google Shopping")

    # Log product quality for debugging
    products_with_images = sum(1 for p in products if p.image_url)
    products_with_urls = sum(1 for p in products if len(p.purchase_url) > 20)
    logger.info(
        f"Product quality: {products_with_images}/{len(products)} have images, "
        f"{products_with_urls}/{len(products)} have real URLs"
    )

    if not products:
        logger.warning("No products found via Google Shopping — using fallback catalog")
        from src.discovery.fallback import get_fallback_products
        products = get_fallback_products()

    if not products:
        logger.error("Still no products (even fallback failed?) - cannot generate trunk")
        raise ValueError("Product discovery completely failed")

    # Phase 3.5 — Firecrawl Verification & Enrichment
    logger.info("Phase 3.5: Verifying size stock and return policies via Firecrawl...")
    from src.discovery.enrichment import enrich_products
    products = await enrich_products(products, profile.sizes)

    if not products:
        logger.error("All products were out of stock during Firecrawl enrichment.")
        raise ValueError("Product enrichment depleted candidate pool")

    # Phase 4 — Outfit Assembly
    logger.info("Phase 4: Assembling outfits...")
    curation = await assemble_outfits(products, brief, profile.photo_path, profile=profile)
    logger.info(f"Assembled {len(curation.outfits)} outfits")

    # Phase 5 — Persist to DB
    logger.info("Phase 5: Saving trunk to database...")
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO trunk (season, stylist_brief, status) VALUES (?, ?, 'pending')",
            (season, brief),
        )
        trunk_id = cursor.lastrowid

        for outfit in curation.outfits:
            for item in outfit.items:
                p = item.product
                conn.execute(
                    """INSERT INTO trunk_item 
                    (trunk_id, product_name, brand, category, color, size, price,
                     retailer, purchase_url, image_url, return_policy_days, return_policy_summary,
                     outfit_group, is_wildcard, stylist_note, outfit_description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        trunk_id, p.product_name, p.brand, p.category, p.color,
                        p.size, p.price, p.retailer, p.purchase_url, p.image_url,
                        p.return_policy_days, p.return_policy_summary, item.outfit_group,
                        1 if item.is_wildcard else 0, item.stylist_note,
                        outfit.outfit_description,
                    ),
                )

    logger.info(f"Trunk #{trunk_id} saved successfully")
    return get_trunk(trunk_id)
async def reroll_outfit(trunk_id: int, outfit_group: int, locked_item_ids: list[int]) -> None:
    profile = get_profile()
    trunk = get_trunk(trunk_id)
    outfit_items = [i for i in trunk.items if i.outfit_group == outfit_group]
    
    if not outfit_items:
        raise ValueError("Outfit not found")
        
    locked_items = [i for i in outfit_items if i.id in locked_item_ids]
    unlocked_items = [i for i in outfit_items if i.id not in locked_item_ids]
    
    if not unlocked_items:
        return  # nothing to reroll
        
    if not locked_items:
        raise ValueError("Please lock at least one outfit piece to reroll the rest.")

    # 1. Delete unlocked items from database for this group
    with get_db() as conn:
        for u in unlocked_items:
            conn.execute("DELETE FROM trunk_item WHERE id = ?", (u.id,))

    # 2. Figure out what's missing
    missing_categories = [i.category for i in unlocked_items]
    locked_desc = "\n".join([f"- {i.category.title()}: {i.color} {i.brand} {i.product_name}" for i in locked_items])
    missing_str = ", ".join(missing_categories)
    
    # 3. Generate Search Queries
    from src.curation.llm_client import call_llm
    from src.config import settings
    
    sys_prompt = "You are an expert personal stylist. Generate highly precise Google Shopping search queries to find replacement clothing."
    user_prompt = f"""I am building an outfit around these existing pieces:
{locked_desc}

I need to find matching items for these missing categories: {missing_str}.
Return 4-6 specific search queries (include color/style that pairs perfectly with the locked items) to find these missing items. Avoid exact color matching (monochrome).

Return JSON format strictly:
{{
  "queries": [
    "Navy blue slim fit chinos men",
    "Outerknown light blue oxford shirt"
  ]
}}"""
    
    res = await call_llm(sys_prompt, user_prompt, model=settings.openrouter_fast_model, temperature=0.7)
    query_texts = res.get("queries", []) if isinstance(res, dict) else []
    
    from src.models import SearchQuery
    from src.discovery.serper import search_products_via_shopping
    q_objs = [SearchQuery(query=q) for q in query_texts]
    candidates = await search_products_via_shopping(q_objs)
    
    from src.discovery.enrichment import enrich_products
    candidates = await enrich_products(candidates, profile.sizes)
    
    if not candidates:
        logger.error("No candidates found for reroll.")
        raise ValueError("Could not find suitable replacements in stock.")
        
    # 4. Pick best candidates
    candidates_text = ""
    for idx, c in enumerate(candidates):
        candidates_text += f"[{idx}] {c.product_name} | {c.brand} | {c.category} | {c.color} | ${c.price}\n"
        
    sys_prompt2 = "You are an expert stylist. Pick the best matching products from the candidates list to complete the outfit."
    user_prompt2 = f"""Locked items:
{locked_desc}

Missing categories to fill: {missing_str}

Candidates:
{candidates_text}

For EACH missing category exactly, pick the ONE best matching product index. Write a concise stylist note explaining why it pairs well with the locked items.

Return JSON strictly:
{{
  "selections": [
    {{"category": "top", "product_index": 2, "stylist_note": "The navy top perfectly contrasts the tan chinos."}}
  ]
}}"""
    
    res2 = await call_llm(sys_prompt2, user_prompt2, temperature=0.5)
    selections = res2.get("selections", []) if isinstance(res2, dict) else []
    
    # 5. Save replacements
    with get_db() as conn:
        for sel in selections:
            idx = sel.get("product_index", -1)
            cat = sel.get("category", "")
            note = sel.get("stylist_note", "Picked as a superior match.")
            if 0 <= idx < len(candidates):
                p = candidates[idx]
                conn.execute(
                    """INSERT INTO trunk_item 
                    (trunk_id, product_name, brand, category, color, size, price,
                     retailer, purchase_url, image_url, return_policy_days, return_policy_summary,
                     outfit_group, is_wildcard, stylist_note, outfit_description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        trunk_id, p.product_name, p.brand, p.category, p.color,
                        p.size, p.price, p.retailer, p.purchase_url, p.image_url,
                        p.return_policy_days, p.return_policy_summary, outfit_group,
                        0, note,
                        "Rerolled outfit piece"
                    ),
                )

def get_trunk(trunk_id: int) -> TrunkResponse:
    """Load a trunk and its items from the database."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM trunk WHERE id = ?", (trunk_id,)).fetchone()
        if not row:
            raise ValueError(f"Trunk {trunk_id} not found")

        items = conn.execute(
            "SELECT * FROM trunk_item WHERE trunk_id = ? ORDER BY outfit_group, id",
            (trunk_id,),
        ).fetchall()

        return TrunkResponse(
            id=row["id"],
            generated_at=str(row["generated_at"]),
            season=row["season"] or "",
            stylist_brief=row["stylist_brief"] or "",
            status=row["status"] or "pending",
            items=[
                TrunkItemResponse(
                    id=i["id"],
                    trunk_id=i["trunk_id"],
                    product_name=i["product_name"] or "Unknown",
                    brand=i["brand"] or "",
                    category=i["category"] or "",
                    color=i["color"] or "",
                    size=i["size"] or "",
                    price=i["price"] or 0.0,
                    retailer=i["retailer"] or "",
                    purchase_url=i["purchase_url"] or "",
                    image_url=i["image_url"] or "",
                    return_policy_days=i["return_policy_days"] or 30,
                    return_policy_summary=i["return_policy_summary"] or "",
                    outfit_group=i["outfit_group"] or 0,
                    is_wildcard=bool(i["is_wildcard"]),
                    decision=i["decision"] or "",
                    returned=bool(i["returned"]),
                    stylist_note=i["stylist_note"] or "",
                    outfit_description=i["outfit_description"] or "",
                    feedback_reason=i["feedback_reason"] or "",
                    feedback_text=i["feedback_text"] or "",
                )
                for i in items
            ],
        )


def get_latest_trunk() -> TrunkResponse | None:
    """Get the most recent trunk."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM trunk ORDER BY generated_at DESC LIMIT 1").fetchone()
        if row:
            return get_trunk(row["id"])
    return None


def list_trunks() -> list[dict]:
    """List all trunks (metadata only) ordered by date descending."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, generated_at, season, status FROM trunk ORDER BY generated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def update_item_decision(item_id: int, decision: str) -> None:
    """Record a purchase/skip decision for a trunk item."""
    if decision not in ("purchase", "skip"):
        raise ValueError(f"Invalid decision: {decision}")

    with get_db() as conn:
        conn.execute(
            "UPDATE trunk_item SET decision = ? WHERE id = ?",
            (decision, item_id),
        )


def mark_item_returned(item_id: int) -> None:
    """Mark a purchased item as returned."""
    with get_db() as conn:
        conn.execute(
            "UPDATE trunk_item SET returned = 1 WHERE id = ? AND decision = 'purchase'",
            (item_id,),
        )


def undo_item_decision(item_id: int) -> None:
    """Reset a purchase/skip decision back to undecided."""
    with get_db() as conn:
        # Reset both decision and returned flag
        conn.execute(
            "UPDATE trunk_item SET decision = NULL, returned = 0 WHERE id = ?",
            (item_id,),
        )


def record_item_feedback(item_id: int, reason: str, text: str) -> None:
    """Record negative feedback (dislike)."""
    with get_db() as conn:
        conn.execute(
            """UPDATE trunk_item 
               SET decision = 'dislike', feedback_reason = ?, feedback_text = ? 
               WHERE id = ?""",
            (reason, text, item_id),
        )
