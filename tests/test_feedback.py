"""Tests for the feedback system — signal strengths and weight adjustment."""

import pytest
from src.feedback.service import record_decision, record_return, record_keep, SIGNAL_MAP
from src.feedback.learner import get_all_weights, adjust_weights, reset_weights
from src.database import get_db


def _create_test_trunk_item(
    brand="J.Crew",
    color="navy",
    category="top",
    price=60.0,
    is_wildcard=0,
):
    """Helper to insert a trunk + item for testing."""
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO trunk (season, stylist_brief, status) VALUES ('winter', 'test brief', 'pending')"
        )
        trunk_id = cursor.lastrowid

        cursor = conn.execute(
            """INSERT INTO trunk_item 
            (trunk_id, product_name, brand, category, color, price, is_wildcard, decision)
            VALUES (?, 'Test Shirt', ?, ?, ?, ?, ?, '')""",
            (trunk_id, brand, category, color, price, is_wildcard),
        )
        return cursor.lastrowid


class TestSignalStrengths:
    """Verify the PRD-specified signal strengths."""

    def test_signal_map_values(self):
        """PRD: skip=-0.5, purchase=+0.5, return=-0.3, keep=+1.0."""
        assert SIGNAL_MAP["skip"] == -0.5
        assert SIGNAL_MAP["purchase"] == 0.5
        assert SIGNAL_MAP["return"] == -0.3
        assert SIGNAL_MAP["keep"] == 1.0


class TestFeedbackRecording:
    """Test feedback recording and weight adjustment."""

    def test_skip_records_negative_signal(self):
        """Skipping an item should create negative weights."""
        item_id = _create_test_trunk_item()
        # Set decision first
        with get_db() as conn:
            conn.execute("UPDATE trunk_item SET decision = 'skip' WHERE id = ?", (item_id,))
        record_decision(item_id, "skip")

        weights = get_all_weights()
        brand_weight = next((w for w in weights if w["dimension"] == "brand" and w["value"] == "J.Crew"), None)
        assert brand_weight is not None
        assert brand_weight["weight"] == -0.5

    def test_purchase_records_positive_signal(self):
        """Purchasing an item should create positive weights."""
        item_id = _create_test_trunk_item(brand="Bonobos", color="olive")
        with get_db() as conn:
            conn.execute("UPDATE trunk_item SET decision = 'purchase' WHERE id = ?", (item_id,))
        record_decision(item_id, "purchase")

        weights = get_all_weights()
        brand_weight = next((w for w in weights if w["dimension"] == "brand" and w["value"] == "Bonobos"), None)
        assert brand_weight is not None
        assert brand_weight["weight"] == 0.5

    def test_keep_records_strong_positive(self):
        """Keeping an item 30+ days should record +1.0 signal."""
        item_id = _create_test_trunk_item()
        with get_db() as conn:
            conn.execute("UPDATE trunk_item SET decision = 'purchase' WHERE id = ?", (item_id,))
        record_keep(item_id)

        weights = get_all_weights()
        brand_weight = next((w for w in weights if w["dimension"] == "brand" and w["value"] == "J.Crew"), None)
        assert brand_weight is not None
        assert brand_weight["weight"] == 1.0

    def test_return_records_mild_negative(self):
        """Returning should give -0.3 (milder than skip)."""
        item_id = _create_test_trunk_item(brand="Nike")
        with get_db() as conn:
            conn.execute("UPDATE trunk_item SET decision = 'purchase' WHERE id = ?", (item_id,))
        record_return(item_id)

        weights = get_all_weights()
        brand_weight = next((w for w in weights if w["dimension"] == "brand" and w["value"] == "Nike"), None)
        assert brand_weight is not None
        assert brand_weight["weight"] == pytest.approx(-0.3)

    def test_wildcard_purchase_gets_bonus(self):
        """Wildcard items should get 1.5x signal when positive."""
        item_id = _create_test_trunk_item(brand="Zara", is_wildcard=1)
        with get_db() as conn:
            conn.execute("UPDATE trunk_item SET decision = 'purchase' WHERE id = ?", (item_id,))
        record_decision(item_id, "purchase")

        weights = get_all_weights()
        brand_weight = next((w for w in weights if w["dimension"] == "brand" and w["value"] == "Zara"), None)
        assert brand_weight is not None
        # 0.5 * 1.5 = 0.75
        assert brand_weight["weight"] == pytest.approx(0.75)

    def test_cumulative_weights(self):
        """Multiple feedbacks on the same dimension should accumulate."""
        # Purchase twice (different items, same brand)
        item1 = _create_test_trunk_item(brand="Gap")
        item2 = _create_test_trunk_item(brand="Gap", color="white")
        
        with get_db() as conn:
            conn.execute("UPDATE trunk_item SET decision = 'purchase' WHERE id IN (?, ?)", (item1, item2))
        
        record_decision(item1, "purchase")
        record_decision(item2, "purchase")

        weights = get_all_weights()
        brand_weight = next((w for w in weights if w["dimension"] == "brand" and w["value"] == "Gap"), None)
        assert brand_weight is not None
        assert brand_weight["weight"] == pytest.approx(1.0)  # 0.5 + 0.5


class TestWeightAdjustment:
    """Test the style_learning weight adjustment directly."""

    def test_adjust_creates_new_weight(self):
        adjust_weights("brand", "TestBrand", 0.5)
        weights = get_all_weights()
        assert any(w["value"] == "TestBrand" for w in weights)

    def test_adjust_updates_existing(self):
        adjust_weights("color", "red", 0.5)
        adjust_weights("color", "red", 0.3)
        weights = get_all_weights()
        red_weight = next(w for w in weights if w["value"] == "red")
        assert red_weight["weight"] == pytest.approx(0.8)

    def test_reset_clears_all(self):
        adjust_weights("brand", "X", 1.0)
        reset_weights()
        assert len(get_all_weights()) == 0

    def test_price_range_bucketing(self):
        """Items should be decomposed into price range buckets."""
        item_id = _create_test_trunk_item(price=75.0)
        with get_db() as conn:
            conn.execute("UPDATE trunk_item SET decision = 'purchase' WHERE id = ?", (item_id,))
        record_decision(item_id, "purchase")

        weights = get_all_weights()
        price_weight = next((w for w in weights if w["dimension"] == "price_range"), None)
        assert price_weight is not None
        assert price_weight["value"] == "60_to_100"
