"""Tests for trunk service — CRUD operations and orchestration."""

import pytest
from src.database import get_db
from src.trunk.service import get_trunk, get_latest_trunk, list_trunks, update_item_decision, mark_item_returned


def _seed_trunk():
    """Seed a trunk with items for testing."""
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO trunk (season, stylist_brief, status) VALUES ('winter', 'Test brief', 'pending')"
        )
        trunk_id = cursor.lastrowid

        items = [
            ("Navy Oxford", "J.Crew", "top", "navy", 59.99, 1, 0),
            ("Olive Chinos", "Bonobos", "bottom", "olive", 89.00, 1, 0),
            ("Red Bomber", "Zara", "outerwear", "red", 99.00, 2, 1),
        ]

        item_ids = []
        for name, brand, cat, color, price, group, wc in items:
            cursor = conn.execute(
                """INSERT INTO trunk_item 
                (trunk_id, product_name, brand, category, color, price, outfit_group, is_wildcard)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (trunk_id, name, brand, cat, color, price, group, wc),
            )
            item_ids.append(cursor.lastrowid)

        return trunk_id, item_ids


class TestTrunkCRUD:
    """Test trunk read operations."""

    def test_get_trunk(self):
        trunk_id, _ = _seed_trunk()
        trunk = get_trunk(trunk_id)
        assert trunk.id == trunk_id
        assert trunk.season == "winter"
        assert len(trunk.items) == 3

    def test_get_trunk_not_found(self):
        with pytest.raises(ValueError):
            get_trunk(99999)

    def test_get_latest_trunk(self):
        _seed_trunk()
        trunk = get_latest_trunk()
        assert trunk is not None
        assert trunk.season == "winter"

    def test_get_latest_trunk_empty(self):
        trunk = get_latest_trunk()
        assert trunk is None

    def test_list_trunks(self):
        _seed_trunk()
        _seed_trunk()
        trunks = list_trunks()
        assert len(trunks) >= 2

    def test_wildcard_flag(self):
        trunk_id, _ = _seed_trunk()
        trunk = get_trunk(trunk_id)
        wildcards = [i for i in trunk.items if i.is_wildcard]
        regulars = [i for i in trunk.items if not i.is_wildcard]
        assert len(wildcards) == 1
        assert len(regulars) == 2


class TestItemDecisions:
    """Test item decision recording."""

    def test_purchase_decision(self):
        trunk_id, item_ids = _seed_trunk()
        update_item_decision(item_ids[0], "purchase")

        trunk = get_trunk(trunk_id)
        item = next(i for i in trunk.items if i.id == item_ids[0])
        assert item.decision == "purchase"

    def test_skip_decision(self):
        trunk_id, item_ids = _seed_trunk()
        update_item_decision(item_ids[0], "skip")

        trunk = get_trunk(trunk_id)
        item = next(i for i in trunk.items if i.id == item_ids[0])
        assert item.decision == "skip"

    def test_invalid_decision_raises(self):
        _, item_ids = _seed_trunk()
        with pytest.raises(ValueError):
            update_item_decision(item_ids[0], "invalid")

    def test_mark_returned(self):
        trunk_id, item_ids = _seed_trunk()
        update_item_decision(item_ids[0], "purchase")
        mark_item_returned(item_ids[0])

        trunk = get_trunk(trunk_id)
        item = next(i for i in trunk.items if i.id == item_ids[0])
        assert item.returned is True

    def test_return_only_purchased(self):
        """Can only return items that were purchased."""
        trunk_id, item_ids = _seed_trunk()
        # Don't set decision to purchase first
        mark_item_returned(item_ids[0])

        trunk = get_trunk(trunk_id)
        item = next(i for i in trunk.items if i.id == item_ids[0])
        assert item.returned is False  # Should not be marked returned
