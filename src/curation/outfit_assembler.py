"""Phase 4 — LLM assembles curated outfits from candidate products."""

import json
import logging

from src.curation.llm_client import call_llm
from src.models import Product, OutfitItem, CurationResult, OutfitAssembly

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


async def assemble_outfits(
    products: list[Product],
    stylist_brief: str,
    photo_path: str = "",
    profile=None,
) -> CurationResult:
    """Use the LLM to select and group products into coherent outfits.

    Args:
        products: Candidate products from Perplexity search.
        stylist_brief: The stylist brief generated in Phase 1.
        photo_path: Optional path to user's full-body photo for additional context.

    Returns:
        CurationResult with 3-4 regular outfits + 1 wildcard outfit.
    """
    # Limit candidates to avoid context window overflow (OpenRouter 400 errors)
    # Shoes and Accessories excluded
    tops = [p for p in products if p.category == 'top'][:60]
    bottoms = [p for p in products if p.category == 'bottom'][:60]
    outer = [p for p in products if p.category == 'outerwear'][:30]
    products = tops + bottoms + outer

    # Cap per-brand to 3 items so one brand doesn't dominate the pool
    from collections import defaultdict
    brand_counts: dict = defaultdict(int)
    capped = []
    for p in products:
        brand_key = (p.brand or "").lower().strip()
        if not brand_key or brand_counts[brand_key] < 3:
            capped.append(p)
            brand_counts[brand_key] += 1
    products = capped

    # Hard budget filter — remove products that exceed the per-category ceiling
    if profile is not None:
        bpc = profile.budget_per_category
        global_max = profile.budget_max
        CAT_BUDGET = {
            "top":       bpc.tops      if bpc.tops      > 0 else global_max,
            "bottom":    bpc.bottoms   if bpc.bottoms   > 0 else global_max,
            "outerwear": bpc.outerwear if bpc.outerwear > 0 else global_max,
        }
        before = len(products)
        products = [
            p for p in products
            if p.price <= 0 or p.price <= CAT_BUDGET.get(p.category, global_max)
        ]
        removed = before - len(products)
        if removed:
            logger.info(f"Budget filter: removed {removed} over-budget items ({before} → {len(products)})")

    # Format products for the LLM
    products_text = ""
    for i, p in enumerate(products):
        tier_label = f" | Tier: {p.formality_tier.upper()}" if p.formality_tier else ""
        products_text += f"""
[{i}] {p.product_name}
    Brand: {p.brand} | Category: {p.category}{tier_label} | Color: {p.color}
    Price: ${p.price:.2f} | Retailer: {p.retailer}
    URL: {p.purchase_url}
    Image: {p.image_url}
"""

    photo_context = ""
    if photo_path:
        photo_context = "\nNote: The client has provided a full-body photo. Consider body proportions and build when selecting items.\n"

    # Build per-category budget constraints
    budget_constraints = ""
    if profile is not None:
        bpc = profile.budget_per_category
        global_max = profile.budget_max
        lines = []
        for cat, val in [("tops", bpc.tops), ("bottoms", bpc.bottoms),
                         ("outerwear", bpc.outerwear)]:
            ceiling = val if val > 0 else global_max
            lines.append(f"  {cat.capitalize()}: max ${ceiling:.0f}")
        budget_constraints = "BUDGET CEILINGS (do not exceed):\n" + "\n".join(lines)
    else:
        budget_constraints = ""

    dealbreaker_rule = ""
    if profile and profile.dislikes:
        dislikes_str = ", ".join(profile.dislikes)
        dealbreaker_rule = f"14. USER DEALBREAKERS: The user HATES: {dislikes_str}. DO NOT pick ANY product that is these or resembles these in any way (e.g. if 'long sleeves', do not pick a henley or long sleeve shirt; if they hate a specific color, avoid it entirely).\n"

    system_prompt = f"""You are an expert men's personal stylist. You have a pool of real products and a client brief.
Your job is to assemble 3-4 coherent outfits PLUS 1 "wildcard" outfit.

CRITICAL OUTFIT COMPOSITION RULES:
1. Every outfit MUST contain AT MINIMUM:
   - ONE top (category = "top") — e.g. t-shirt, polo, oxford shirt, henley
   - EXACTLY ONE bottom (category = "bottom") — Do NOT include multiple bottoms.
2. UNIQUE ITEMS ONLY: Do NOT reuse the same product (same product_index) in multiple outfits.
3. Outfits MAY ALSO include:
   - Outerwear (jacket, sweater, blazer) — ONLY as an additional layer on top of a base top
4. NEVER create an outfit with a bottom + outerwear but NO base layer top.
5. FORMALITY TIER PAIRING LAW: A top and bottom must be within 1 formality tier of each other.
   Tier order (lowest→highest): athletic < casual < smart_casual < formal
   - ILLEGAL: polo (SMART_CASUAL) + workout shorts (ATHLETIC)
   - ILLEGAL: dress trousers (SMART_CASUAL) + graphic tee (CASUAL) — 2 tiers apart
   - LEGAL: polo (SMART_CASUAL) + chinos (CASUAL or SMART_CASUAL)
   - LEGAL: t-shirt (CASUAL) + jeans (CASUAL)
6. DO NOT include Accessories (belts, watches, sunglasses, wallets).
7. DO NOT include Shoes — they are handled separately.
8. COLOR RULES: No monochromatic outfits. Enforce contrast (navy + white/grey, olive + tan/cream).
9. Ensure variety across outfits — don't repeat the same brand or color palette. BRAND DIVERSITY: No single brand should appear in more than 2 outfits total.
10. The WILDCARD outfit (outfit_group = 5) should intentionally break from stated preferences.
11. Write a brief stylist note for each item explaining why it was chosen.
12. Only use items from the provided product list (reference by index number).
13. outfit_group MUST be an integer (1, 2, 3, 4, 5).
{dealbreaker_rule}

{budget_constraints}

**CRITICAL RULES OVERRIDE (USER PERSONA DOCUMENT):**
{_get_user_persona()}

You must read the user persona rules and STRICTLY ADHERE to its guidelines (brands, sizing, colors, aesthetics, budget, fits, rules).

Return valid JSON matching this structure:
{{
  "outfits": [
    {{
      "outfit_group": 1,
      "is_wildcard": false,
      "outfit_description": "Smart casual weekend look",
      "items": [
        {{"product_index": 0, "stylist_note": "Classic navy oxford as the base layer..."}},
        {{"product_index": 3, "stylist_note": "Slim chinos complement the oxford..."}}
      ]
    }}
  ]
}}"""

    user_prompt = f"""**Stylist Brief:**
{stylist_brief}
{photo_context}
**Available Products ({len(products)} candidates):**
{products_text}

Please assemble 3-4 regular outfits + 1 wildcard outfit from these products."""

    result = await call_llm(system_prompt, user_prompt, temperature=0.7, max_tokens=4096)

    # Parse the LLM response into our data model
    outfits = []
    if isinstance(result, dict) and "outfits" in result:
        for outfit_data in result["outfits"]:
            items = []
            for item_data in outfit_data.get("items", []):
                idx = item_data.get("product_index", 0)
                if 0 <= idx < len(products):
                    items.append(OutfitItem(
                        product=products[idx],
                        outfit_group=outfit_data.get("outfit_group", 0),
                        is_wildcard=outfit_data.get("is_wildcard", False),
                        stylist_note=item_data.get("stylist_note", ""),
                    ))

            if items:
                outfits.append(OutfitAssembly(
                    outfit_group=outfit_data.get("outfit_group", 0),
                    is_wildcard=outfit_data.get("is_wildcard", False),
                    items=items,
                    outfit_description=outfit_data.get("outfit_description", ""),
                ))

    # ── Post-assembly validation: ensure every outfit has top + bottom ──
    outfits = _validate_outfit_composition(outfits, products)

    return CurationResult(outfits=outfits)


def _validate_outfit_composition(
    outfits: list[OutfitAssembly],
    products: list[Product],
) -> list[OutfitAssembly]:
    """Validate and fix outfit composition — every outfit MUST have a top and bottom.

    If an outfit is missing a top or bottom, tries to auto-fill from the
    available product pool. If it can't be fixed, the outfit is dropped.
    """
    # Deduplicate items across outfits first (LLM sometimes reuses items)
    seen_identifiers = set()
    for outfit in outfits:
        deduped = []
        for item in outfit.items:
            key = (item.product.product_name, item.product.purchase_url)
            if key not in seen_identifiers:
                seen_identifiers.add(key)
                deduped.append(item)
            else:
                logger.warning(f"Removed duplicate item '{item.product.product_name}' from Outfit {outfit.outfit_group}")
        outfit.items = deduped

    # Build pools of available tops and bottoms not already used
    used_indices = set()
    for outfit in outfits:
        for item in outfit.items:
            # Find the product index
            for i, p in enumerate(products):
                if (p.product_name == item.product.product_name
                        and p.purchase_url == item.product.purchase_url):
                    used_indices.add(i)
                    break

    available_tops = [
        (i, p) for i, p in enumerate(products)
        if p.category == "top" and i not in used_indices
    ]
    available_bottoms = [
        (i, p) for i, p in enumerate(products)
        if p.category == "bottom" and i not in used_indices
    ]

    validated = []
    for outfit in outfits:
        # Check for multiple bottoms and fix
        bottoms = [item for item in outfit.items if item.product.category == "bottom"]
        if len(bottoms) > 1:
            # Keep only the first one to avoid "two bottoms" issue
            outfit.items = [item for item in outfit.items if item.product.category != "bottom"]
            outfit.items.append(bottoms[0])
            logger.warning(f"Outfit {outfit.outfit_group}: Removed {len(bottoms)-1} extra bottom(s), kept '{bottoms[0].product.product_name}'")

        categories = [item.product.category for item in outfit.items]
        has_top = "top" in categories
        has_bottom = "bottom" in categories

        if has_top and has_bottom:
            validated.append(outfit)
            continue

        # Try to fix missing pieces
        if not has_top and available_tops:
            idx, top_product = available_tops.pop(0)
            used_indices.add(idx)
            outfit.items.append(OutfitItem(
                product=top_product,
                outfit_group=outfit.outfit_group,
                is_wildcard=outfit.is_wildcard,
                stylist_note="Auto-added base layer to complete the outfit.",
            ))
            logger.warning(
                f"Outfit {outfit.outfit_group}: missing top — auto-added '{top_product.product_name}'"
            )
            has_top = True

        if not has_bottom and available_bottoms:
            idx, bottom_product = available_bottoms.pop(0)
            used_indices.add(idx)
            outfit.items.append(OutfitItem(
                product=bottom_product,
                outfit_group=outfit.outfit_group,
                is_wildcard=outfit.is_wildcard,
                stylist_note="Auto-added bottoms to complete the outfit.",
            ))
            logger.warning(
                f"Outfit {outfit.outfit_group}: missing bottom — auto-added '{bottom_product.product_name}'"
            )
            has_bottom = True

        if has_top and has_bottom:
            validated.append(outfit)
        else:
            missing = []
            if not has_top:
                missing.append("top")
            if not has_bottom:
                missing.append("bottom")
            logger.error(
                f"Outfit {outfit.outfit_group} dropped — missing {', '.join(missing)} "
                f"and no available products to fill. Items were: {[i.product.product_name for i in outfit.items]}"
            )

    logger.info(
        f"Outfit validation: {len(validated)}/{len(outfits)} outfits passed "
        f"(tops available: {len(available_tops)}, bottoms available: {len(available_bottoms)})"
    )
    return validated
