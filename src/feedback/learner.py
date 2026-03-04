"""Style learning — adjusts weights in the style_learning table."""

import logging
from src.database import get_db

logger = logging.getLogger(__name__)


def adjust_weights(dimension: str, value: str, signal: float):
    """Adjust the cumulative weight for a style dimension/value pair.

    Uses UPSERT to create or update the weight.

    Args:
        dimension: Style dimension (brand, color, category, fit, price_range).
        value: The specific value (e.g., "J.Crew", "navy", "chinos").
        signal: Signal strength to add to the weight.
    """
    with get_db() as conn:
        conn.execute(
            """INSERT INTO style_learning (dimension, value, weight, updated_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(dimension, value)
               DO UPDATE SET
                 weight = weight + excluded.weight,
                 updated_at = CURRENT_TIMESTAMP""",
            (dimension, value, signal),
        )

    logger.debug(f"Weight adjusted: {dimension}={value} signal={signal:+.2f}")


def get_all_weights() -> list[dict]:
    """Get all style learning weights ordered by absolute magnitude."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT dimension, value, weight FROM style_learning ORDER BY ABS(weight) DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def reset_weights():
    """Reset all style learning weights (for testing/debugging)."""
    with get_db() as conn:
        conn.execute("DELETE FROM style_learning")
    logger.info("All style learning weights reset")
