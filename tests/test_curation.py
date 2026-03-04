"""Tests for the curation pipeline — stylist brief and outfit assembly."""

import pytest
from unittest.mock import AsyncMock, patch

from src.models import UserProfile, Product, CurationResult


class TestStylistBrief:
    """Test stylist brief generation."""

    @pytest.mark.asyncio
    async def test_brief_generation(self):
        """Verify brief generation returns a string."""
        mock_response = {
            "brief": "Client is 5'11, medium build. Prefers slim-fit casual wear in navy and olive."
        }

        with patch("src.curation.stylist_brief.call_llm", new_callable=AsyncMock, return_value=mock_response):
            from src.curation.stylist_brief import generate_stylist_brief
            brief = await generate_stylist_brief(UserProfile())

        assert isinstance(brief, str)
        assert len(brief) > 0


class TestOutfitAssembly:
    """Test outfit assembly from products."""

    @pytest.mark.asyncio
    async def test_assembly_creates_outfits(self):
        """Verify outfit assembly returns structured outfits."""
        products = [
            Product(product_name="Navy Oxford", brand="J.Crew", category="top", color="navy", price=59.99),
            Product(product_name="Olive Chinos", brand="Bonobos", category="bottom", color="olive", price=89.00),
            Product(product_name="Red Bomber Jacket", brand="Zara", category="outerwear", color="red", price=99.00),
            Product(product_name="White Tee", brand="Hanes", category="top", color="white", price=15.00),
            Product(product_name="Jeans", brand="Levis", category="bottom", color="blue", price=60.00),
        ]

        mock_response = {
            "outfits": [
                {
                    "outfit_group": 1,
                    "is_wildcard": False,
                    "outfit_description": "Smart casual weekend",
                    "items": [
                        {"product_index": 0, "stylist_note": "Classic navy oxford"},
                        {"product_index": 2, "stylist_note": "Olive pairs well"},
                    ],
                },
                {
                    "outfit_group": 2,
                    "is_wildcard": True,
                    "outfit_description": "Bold street style",
                    "items": [
                        {"product_index": 4, "stylist_note": "Breaking from usual palette"},
                        {"product_index": 1, "stylist_note": "Base layer"},
                        {"product_index": 3, "stylist_note": "Base jeans"},
                    ],
                },
            ]
        }

        with patch("src.curation.outfit_assembler.call_llm", new_callable=AsyncMock, return_value=mock_response):
            from src.curation.outfit_assembler import assemble_outfits
            result = await assemble_outfits(products, "Test brief")

        assert isinstance(result, CurationResult)
        assert len(result.outfits) == 2
        assert result.outfits[0].is_wildcard is False
        assert result.outfits[1].is_wildcard is True
        assert len(result.outfits[0].items) == 2
        assert len(result.outfits[1].items) == 3

    @pytest.mark.asyncio
    async def test_assembly_handles_invalid_indices(self):
        """Product indices out of range should be skipped."""
        products = [
            Product(product_name="Only Product", brand="Test", category="top", price=50.0),
            Product(product_name="Bottom Product", brand="Test", category="bottom", price=50.0),
        ]

        mock_response = {
            "outfits": [
                {
                    "outfit_group": 1,
                    "is_wildcard": False,
                    "items": [
                        {"product_index": 0, "stylist_note": "Valid"},
                        {"product_index": 99, "stylist_note": "Invalid index"},
                    ],
                }
            ]
        }

        with patch("src.curation.outfit_assembler.call_llm", new_callable=AsyncMock, return_value=mock_response):
            from src.curation.outfit_assembler import assemble_outfits
            result = await assemble_outfits(products, "Test brief")

        # The invalid index is dropped. Then _validate_outfit_composition auto-adds the missing bottom!
        assert len(result.outfits[0].items) == 2
        categories = [item.product.category for item in result.outfits[0].items]
        assert "top" in categories
        assert "bottom" in categories
