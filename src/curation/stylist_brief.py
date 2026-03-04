"""Phase 1 — Generate the stylist brief from profile + feedback history + season."""

import json
import logging
from datetime import datetime

from src.curation.llm_client import call_llm
from src.models import UserProfile, StyleWeight
from src.database import get_db

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


def _get_current_season() -> str:
    """Determine current season from the date."""
    month = datetime.now().month
    if month in (3, 4, 5):
        return "spring"
    elif month in (6, 7, 8):
        return "summer"
    elif month in (9, 10, 11):
        return "fall"
    else:
        return "winter"


def _get_season_context() -> str:
    """Get a more descriptive season context."""
    month = datetime.now().month
    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    season = _get_current_season()
    month_name = month_names[month]

    early_late = "early" if datetime.now().day <= 15 else "late"
    return f"{early_late} {month_name} ({season})"


def _get_style_weights() -> list[StyleWeight]:
    """Load learned style weights from the database."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT dimension, value, weight FROM style_learning ORDER BY ABS(weight) DESC LIMIT 30"
        ).fetchall()
        return [StyleWeight(dimension=r["dimension"], value=r["value"], weight=r["weight"]) for r in rows]


def _get_recent_feedback_text(limit=5) -> list[str]:
    """Get recent explicit feedback text from dislikes."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT feedback_text, feedback_reason, product_name FROM trunk_item "
            "WHERE decision='dislike' AND feedback_text != '' "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [f"Disliked '{r['product_name']}' ({r['feedback_reason']}): {r['feedback_text']}" for r in rows]


async def generate_stylist_brief(profile: UserProfile) -> str:
    """Generate a natural-language stylist brief for the LLM curation phase.

    Combines user profile, learned preferences, and seasonal context.
    """
    season_ctx = _get_season_context()
    weights = _get_style_weights()
    recent_feedback = _get_recent_feedback_text()
    persona_doc = _get_user_persona()

    # Format learned preferences
    liked = [w for w in weights if w.weight > 0]
    disliked = [w for w in weights if w.weight < 0]

    likes_text = ", ".join(f"{w.value} ({w.dimension}, +{w.weight:.1f})" for w in liked[:10]) if liked else "No data yet"
    dislikes_text = ", ".join(f"{w.value} ({w.dimension}, {w.weight:.1f})" for w in disliked[:10]) if disliked else "No data yet"
    feedback_text = "\n".join(f"- {t}" for t in recent_feedback)

    # Logic for Casual Vibe
    vibe_instructions = ""
    if profile.occasion and profile.occasion.lower() == "casual":
        vibe_instructions = (
            "STRICT: Casual vibe. Bottoms should be ~60% jeans, 30% chinos, 10% other casual. "
            "NEVER suggest slacks/dress trousers (too formal) or joggers/sweatpants (too athleisure). "
            "Tops: t-shirts, henleys, casual flannels, casual button-downs. No graphic tees. "
            "Ensure color contrast — navy top + tan chinos, not all-navy."
        )

    system_prompt = """You are an expert men's personal stylist AI. Your job is to write a concise stylist brief 
that will guide product search and outfit curation for a client. 

Write in third person, professional tone. Include all relevant details that would help 
another stylist pick the right items. The brief should be 3-5 sentences."""

    user_prompt = f"""Create a stylist brief for this client:

**Profile:**
- Height: {profile.height or 'Not specified'}
- Skin tone: {profile.skin_color or 'Not specified'}
- Fit preference (tops): {profile.fit_preference}
- Bottom fit: {profile.bottom_fit} fit
- Bottom rise: {profile.bottom_rise}-rise
- Occasion/vibe: {profile.occasion}
- Preferred colors: {', '.join(profile.colors_preferred) if profile.colors_preferred else 'No preference'}
- Budget: ${profile.budget_min:.0f}–${profile.budget_max:.0f} per item
- Per-category budget: tops=${profile.budget_per_category.tops or profile.budget_max:.0f}, bottoms=${profile.budget_per_category.bottoms or profile.budget_max:.0f}, outerwear=${profile.budget_per_category.outerwear or profile.budget_max:.0f}
- Measurements: {profile.measurements.model_dump_json()}
- Sizes: {profile.sizes.model_dump_json()}
- Style notes: {profile.style_notes or 'None'}
- Preferred Brands: {', '.join(profile.brands_liked) if profile.brands_liked else 'None'}
- DISLIKES / DEALBREAKERS: {', '.join(profile.dislikes) if profile.dislikes else 'None'}

**Learned preferences (from past feedback):**
- Tends to keep: {likes_text}
- Tends to skip/return: {dislikes_text}

**Recent Explicit Feedback:**
{feedback_text or 'None'}

**Current season:** {season_ctx}

{vibe_instructions}

**CRITICAL USER PERSONA DOCUMENT (MUST OVERRIDE ALL OTHER PREFERENCES):**
{persona_doc}

**Instructions:**
1. Write a 3-5 sentence stylist brief in third person.
2. Explicitly list 3-5 'Discovery Brands' that are similar to the client's preferred brands but are STRICTLY NOT in the 'Preferred Brands' list. Label them as 'New Brand Discoveries'.
3. Ensure recommendations follow the vibe constraints.
4. The client dislikes monochromatic outfits (e.g. all black). Emphasize mixing colors (e.g. Navy top + Grey bottom).
5. STRONGLY ADHERE to the rules, measurements, fits, and brand preferences stated in the USER PERSONA DOCUMENT.

Return JSON: {{"brief": "..."}}"""

    result = await call_llm(system_prompt, user_prompt, temperature=0.6)

    if isinstance(result, dict) and "brief" in result:
        return result["brief"]
    elif isinstance(result, str):
        return result

    return str(result)
