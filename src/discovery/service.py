"""Service for the Discover feature: fetching trending items and handling user feedback."""

import logging
import random
from src.database import get_db
from src.discovery.serper import search_shopping, _extract_color_from_text
from src.models import Product

logger = logging.getLogger(__name__)

# Exploratory queries — named-brand specific so one brand can't dominate via generic searches
TRENDING_QUERIES = [
    # Tops — diverse brands
    "Buck Mason t-shirt men",
    "Cuts Clothing henley men",
    "True Classic crew neck men",
    "Outerknown linen shirt men",
    "Taylor Stitch oxford shirt men",
    "Rails flannel shirt men",
    "Roark flannel shirt men",
    "Rhone polo shirt men",
    "Onia linen shirt men",
    "Richer Poorer henley men",
    "Reigning Champ sweatshirt men",
    "Todd Snyder hoodie men",
    "Alex Mill t-shirt men",
    "Frank And Oak button-down men",
    "Vince cotton t-shirt men",
    "Club Monaco button-down men",
    "Entireworld sweatshirt men",
    "Billy Reid linen shirt men",
    "Saturdays NYC shirt men",
    "GANT oxford shirt men",
    "Norse Projects t-shirt men",
    # Bottoms — diverse brands
    "Bonobos slim chino men",
    "Madewell slim jeans men",
    "Everlane slim chino men",
    "Corridor slim jean men",
    "Alex Mill chino men",
    "Levi's 511 slim jeans men",
    "Lucky Brand jeans men",
    "NN07 chino men",
    "Stan Ray work pant men",
    "Carhartt WIP chino men",
    "A.P.C. slim jean men",
    "Universal Works chino men",
    "Oliver Spencer chino men",
    # Outerwear & sweaters
    "Patagonia fleece jacket men",
    "Banana Republic merino sweater men",
    "Peter Millar quarter-zip sweater men",
    "Southern Tide fleece jacket men",
    "Vuori performance jacket men",
    "Todd Snyder blazer men",
    "Hartford cardigan men",
]

# Article type keyword map — ordered by specificity
_ARTICLE_TYPE_MAP = [
    ("polo", "polo"),
    ("henley", "henley"),
    ("oxford shirt", "oxford shirt"),
    ("button-down", "button-down shirt"),
    ("button down", "button-down shirt"),
    ("linen shirt", "linen shirt"),
    ("flannel shirt", "flannel shirt"),
    ("hoodie", "hoodie"),
    ("sweatshirt", "sweatshirt"),
    ("crewneck", "crewneck"),
    ("crew neck", "crewneck"),
    ("t-shirt", "t-shirt"),
    ("tee", "t-shirt"),
    ("chino", "chinos"),
    ("trouser", "trousers"),
    ("jean", "jeans"),
    ("denim", "jeans"),
    ("jogger", "joggers"),
    ("sweatpant", "joggers"),
    ("short", "shorts"),
    ("sweater", "sweater"),
    ("cardigan", "cardigan"),
    ("blazer", "blazer"),
    ("jacket", "jacket"),
    ("boot", "boots"),
    ("sneaker", "sneakers"),
    ("loafer", "loafers"),
]


def _extract_article_type(name: str) -> str:
    """Extract granular article type (polo, jeans, chinos…) from a product name."""
    n = name.lower()
    for keyword, article in _ARTICLE_TYPE_MAP:
        if keyword in n:
            return article
    return ""


def _build_personalized_queries(n_queries: int = 4) -> list[str]:
    """Build targeted search queries from accumulated style_learning weights."""
    with get_db() as conn:
        liked_brands = [
            r["value"] for r in conn.execute(
                "SELECT value FROM style_learning WHERE dimension='brand' AND weight > 0.5 "
                "ORDER BY weight DESC LIMIT 5"
            ).fetchall()
        ]
        liked_colors = [
            r["value"] for r in conn.execute(
                "SELECT value FROM style_learning WHERE dimension='color' AND weight > 0 "
                "ORDER BY weight DESC LIMIT 4"
            ).fetchall()
        ]
        liked_articles = [
            r["value"] for r in conn.execute(
                "SELECT value FROM style_learning WHERE dimension='article_type' AND weight > 0 "
                "ORDER BY weight DESC LIMIT 5"
            ).fetchall()
        ]
        liked_cats = [
            r["value"] for r in conn.execute(
                "SELECT value FROM style_learning WHERE dimension='category' AND weight > 0 "
                "ORDER BY weight DESC LIMIT 3"
            ).fetchall()
        ]

    queries: list[str] = []

    # Most specific: brand + article_type (e.g. "Vuori henley men")
    for brand in liked_brands[:3]:
        for article in liked_articles[:2]:
            queries.append(f"{brand} {article} men")

    # Brand + top color (e.g. "Bonobos chinos olive men")
    for brand in liked_brands[:2]:
        for color in liked_colors[:2]:
            cat = liked_cats[0] if liked_cats else "shirt"
            queries.append(f"{brand} {cat} {color} men")

    # Color + article (broadens brand exposure while keeping style signal)
    for color in liked_colors[:2]:
        for article in liked_articles[:2]:
            queries.append(f"{color} {article} men")

    # Shuffle and cap
    random.shuffle(queries)
    return queries[:n_queries]


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

from src.curation.llm_client import call_llm
from src.config import settings

async def _generate_persona_discovery_queries(n_queries: int = 5) -> list[str]:
    """Generate intelligent exploratory queries based on the user's persona document."""
    persona_doc = _get_user_persona()
    
    system_prompt = f"""You are a men's personal stylist. Your task is to generate {n_queries} diverse search queries to help your client discover new clothing items that strictly adhere to their persona.

Rules for queries:
1. They must represent single products (e.g. "Buck Mason curved hem tee men", "Lululemon ABC Trouser men").
2. DO NOT output shoe queries. Focus on tops, bottoms, and outerwear.
3. Keep queries concise (Brand + Style/Fit + Category + Color + "men").
4. MUST ADHERE TO THE USER PERSONA BELOW. Focus heavily on brands they like, or brands extremely similar to their trusted roster. 
5. NEVER recommend items that violate their dealbreakers or body type logic (e.g. no slim rigid pants if they have athletic thighs, no long sleeves if they hate long sleeves).

**USER PERSONA:**
{persona_doc}

Return valid JSON matching this structure:
{{"queries": ["query1", "query2"]}}"""

    user_prompt = f"Generate {n_queries} discovery queries."
    
    result = await call_llm(system_prompt, user_prompt, temperature=0.7, max_tokens=1000)
    if isinstance(result, dict) and "queries" in result:
        return result["queries"][:n_queries]
    
    return [
        "Buck Mason curved hem slub tee men",
        "Banana Republic rapid movement chino athletic taper men",
        "American Eagle Airflex+ slim jeans men",
        "Lululemon ABC Trouser classic fit men",
        "UNTUCKit short sleeve collared shirt men"
    ][:n_queries]

async def get_discovery_feed(limit: int = 10) -> list[dict]:
    """Get a feed of unvoted items, personalised based on accumulated likes."""
    # 1. Return existing unvoted items first
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM discovery_item WHERE decision IS NULL ORDER BY RANDOM() LIMIT ?",
            (limit,)
        ).fetchall()
        items = [dict(r) for r in rows]

    if len(items) >= limit:
        return items

    needed = limit - len(items)

    # 2. Decide personalization level based on total likes so far
    with get_db() as conn:
        total_likes = conn.execute(
            "SELECT COUNT(*) FROM discovery_item WHERE decision='like'"
        ).fetchone()[0]

    if total_likes >= 10:
        personalized_share = 0.7   # 70% personalized, 30% exploratory
    elif total_likes >= 3:
        personalized_share = 0.4   # 40% personalized
    else:
        personalized_share = 0.0   # pure exploration until 3 likes

    n_personalized = int(needed * personalized_share)
    n_exploratory = needed - n_personalized

    queries_to_run: list[str] = []
    if n_personalized > 0:
        personalized = _build_personalized_queries(n_personalized)
        queries_to_run.extend(personalized)
        logger.info(f"Discovery: {len(personalized)} personalized queries (total_likes={total_likes})")

    if n_exploratory > 0:
        logger.info(f"Discovery: Generating {n_exploratory} exploratory queries via LLM...")
        exploring_queries = await _generate_persona_discovery_queries(n_exploratory)
        queries_to_run.extend(exploring_queries)
        logger.info(f"Discovery: Added {len(exploring_queries)} persona-guided exploratory queries")

    # 3. Fetch and save new items
    try:
        with get_db() as conn:
            for query in queries_to_run:
                products = await search_shopping(query, num_results=8)
                for p in products:
                    color = p.color or _extract_color_from_text(p.product_name)
                    article_type = _extract_article_type(p.product_name)
                    # Cap: skip if this brand already has ≥ 3 undecided items in the pool
                    if p.brand:
                        existing = conn.execute(
                            "SELECT COUNT(*) FROM discovery_item WHERE brand = ? AND decision IS NULL",
                            (p.brand,)
                        ).fetchone()[0]
                        if existing >= 3:
                            logger.debug(f"Discovery brand cap: skipping '{p.brand}' ({existing} undecided)")
                            continue
                    try:
                        conn.execute(
                            """INSERT OR IGNORE INTO discovery_item
                               (product_name, brand, category, color, article_type,
                                image_url, purchase_url, price)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (p.product_name, p.brand, p.category, color, article_type,
                             p.image_url, p.purchase_url, p.price)
                        )
                    except Exception as e:
                        logger.warning(f"Failed to save discovery item: {e}")
    except Exception as e:
        logger.error(f"Failed to fetch discovery items: {e}")

    # 4. Re-fetch including newly saved items
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM discovery_item WHERE decision IS NULL ORDER BY RANDOM() LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def record_discovery_feedback(item_id: int, decision: str):
    """Record user feedback (like/dislike) and update style weights across all dimensions."""
    if decision not in ('like', 'dislike'):
        raise ValueError("Invalid decision")

    with get_db() as conn:
        item = conn.execute(
            "SELECT * FROM discovery_item WHERE id = ?", (item_id,)
        ).fetchone()
        if not item:
            logger.warning(f"Discovery item {item_id} not found")
            return

        conn.execute(
            "UPDATE discovery_item SET decision = ? WHERE id = ?", (decision, item_id)
        )

    # Signal strength: like = +1.0, dislike = -0.5
    # Dislikes are softer — we don't want one bad pick to bury a brand forever
    weight = 1.0 if decision == "like" else -0.5

    dimensions: list[tuple[str, str, float]] = []

    if item["brand"]:
        dimensions.append(("brand", item["brand"], weight))

    if item["category"]:
        # Category gets a smaller nudge — less specific than brand/article
        dimensions.append(("category", item["category"], weight * 0.3))

    # Color preference — only track on likes (don't anti-learn colors from one dislike)
    color = item["color"] if "color" in item.keys() else ""
    if color and decision == "like":
        dimensions.append(("color", color, weight * 0.5))

    # Article type — most specific style signal
    article_type = item["article_type"] if "article_type" in item.keys() else ""
    if article_type:
        dimensions.append(("article_type", article_type, weight * 0.8))

    with get_db() as conn:
        for dimension, value, w in dimensions:
            conn.execute(
                """INSERT INTO style_learning (dimension, value, weight, updated_at)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(dimension, value) DO UPDATE SET
                     weight = weight + excluded.weight,
                     updated_at = CURRENT_TIMESTAMP""",
                (dimension, value, w)
            )

    logger.info(
        f"Discovery feedback: item={item_id} decision={decision} "
        f"brand={item['brand']} article={article_type} color={color}"
    )
