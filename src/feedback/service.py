"""Feedback service — record decisions and compute signal strengths."""

import logging
from src.database import get_db
from src.feedback.learner import adjust_weights

logger = logging.getLogger(__name__)

# Signal strengths per PRD
SIGNAL_MAP = {
    "skip": -0.5,
    "purchase": 0.5,
    "return": -0.3,
    "keep": 1.0,
    "dislike": -1.0,
}


def _get_item_dimensions(item_id: int) -> dict:
    """Extract style dimensions from a trunk item for weight adjustment."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT brand, color, category, price FROM trunk_item WHERE id = ?",
            (item_id,),
        ).fetchone()

        if not row:
            return {}

        dimensions = {}
        if row["brand"]:
            dimensions["brand"] = row["brand"]
        if row["color"]:
            dimensions["color"] = row["color"]
        if row["category"]:
            dimensions["category"] = row["category"]

        # Derive price range bucket
        price = row["price"]
        if price > 0:
            if price < 30:
                dimensions["price_range"] = "under_30"
            elif price < 60:
                dimensions["price_range"] = "30_to_60"
            elif price < 100:
                dimensions["price_range"] = "60_to_100"
            elif price < 150:
                dimensions["price_range"] = "100_to_150"
            else:
                dimensions["price_range"] = "150_plus"

        return dimensions


def _record_feedback(item_id: int, action: str, reason_filter: str = None):
    """Record a feedback entry and trigger weight adjustment."""
    signal = SIGNAL_MAP.get(action)
    if signal is None:
        raise ValueError(f"Unknown action: {action}")

    with get_db() as conn:
        conn.execute(
            "INSERT INTO feedback (trunk_item_id, action, signal_strength, reason) VALUES (?, ?, ?, ?)",
            (item_id, action, signal, reason_filter or ''),
        )

    # Get item dimensions and adjust weights
    dimensions = _get_item_dimensions(item_id)
    
    # Filter dimensions if specific reason given (e.g. Color -> only adjust color weight)
    if reason_filter:
        dimensions = {k: v for k, v in dimensions.items() if k.lower() == reason_filter.lower()}

    # Check if item is wildcard — wildcard feedback gets extra weight
    with get_db() as conn:
        row = conn.execute("SELECT is_wildcard FROM trunk_item WHERE id = ?", (item_id,)).fetchone()
        is_wildcard = bool(row["is_wildcard"]) if row else False

    # Wildcard purchases/keeps get 1.5x signal (strong discovery signal)
    multiplier = 1.5 if is_wildcard and signal > 0 else 1.0

    for dimension, value in dimensions.items():
        adjust_weights(dimension, value, signal * multiplier)

    logger.info(f"Feedback recorded: item={item_id}, action={action}, signal={signal}, filter={reason_filter}")


def record_decision(item_id: int, decision: str):
    """Record a purchase or skip decision."""
    _record_feedback(item_id, decision)


def record_return(item_id: int):
    """Record a return."""
    _record_feedback(item_id, "return")


def record_keep(item_id: int):
    """Record a keep (item retained 30+ days)."""
    _record_feedback(item_id, "keep")


def record_dislike(item_id: int, reason: str = ""):
    """Record a strong dislike with optional reason filter."""
    # Map UI reasons to dimensions
    reason_map = {
        "Color": "color",
        "Article": "category",
        # "Style" affects all dimensions (None)
    }
    filter_dim = reason_map.get(reason)

    _record_feedback(item_id, "dislike", reason_filter=filter_dim)
