"""Tests for the discovery pipeline — search queries and product parsing."""

import pytest
from unittest.mock import AsyncMock, patch

from src.models import SearchQuery, Product


class TestSearchQueries:
    """Test search query generation."""

    @pytest.mark.asyncio
    async def test_generate_queries_returns_list(self):
        """Verify query generation returns SearchQuery objects."""
        mock_response = {
            "queries": [
                {"query": "J.Crew slim fit oxford navy men", "target_category": "top", "is_wildcard": False},
                {"query": "Bonobos stretch chinos olive men", "target_category": "bottom", "is_wildcard": False},
                {"query": "Allbirds wool runners men casual", "target_category": "shoes", "is_wildcard": True},
            ]
        }

        with patch("src.discovery.search_queries.call_llm", new_callable=AsyncMock, return_value=mock_response):
            from src.discovery.search_queries import generate_search_queries
            queries = await generate_search_queries("Test brief: slim fit casual wear")

        assert len(queries) == 3
        assert all(isinstance(q, SearchQuery) for q in queries)
        assert queries[2].is_wildcard is True

    @pytest.mark.asyncio
    async def test_wildcard_queries_included(self):
        """Verify wildcard queries are generated."""
        mock_response = {
            "queries": [
                {"query": "basic query", "target_category": "top", "is_wildcard": False},
                {"query": "wildcard query", "target_category": "top", "is_wildcard": True},
            ]
        }

        with patch("src.discovery.search_queries.call_llm", new_callable=AsyncMock, return_value=mock_response):
            from src.discovery.search_queries import generate_search_queries
            queries = await generate_search_queries("Test brief")

        wildcard_count = sum(1 for q in queries if q.is_wildcard)
        assert wildcard_count >= 1


class TestProductParsing:
    """Test product parsing from raw search results."""

    @pytest.mark.asyncio
    async def test_parse_products_from_raw(self):
        """Verify product parsing extracts structured data."""
        mock_response = {
            "products": [
                {
                    "product_name": "Slim Fit Oxford Shirt",
                    "brand": "J.Crew",
                    "category": "top",
                    "color": "navy",
                    "price": 59.99,
                    "retailer": "J.Crew",
                    "purchase_url": "https://jcrew.com/shirt",
                    "image_url": "https://jcrew.com/img.jpg",
                    "return_policy_days": 30,
                },
                {
                    "product_name": "Stretch Chinos",
                    "brand": "Bonobos",
                    "category": "bottom",
                    "color": "olive",
                    "price": 89.00,
                    "retailer": "Bonobos",
                    "purchase_url": "https://bonobos.com/chinos",
                    "image_url": "https://bonobos.com/img.jpg",
                    "return_policy_days": 45,
                },
            ]
        }

        with patch("src.discovery.product_parser.call_llm", new_callable=AsyncMock, return_value=mock_response):
            from src.discovery.product_parser import parse_products
            products = await parse_products(["raw search text"])

        assert len(products) == 2
        assert all(isinstance(p, Product) for p in products)
        assert products[0].brand == "J.Crew"
        assert products[1].price == 89.00

    @pytest.mark.asyncio
    async def test_parse_handles_empty_results(self):
        """Empty search results should return empty list."""
        from src.discovery.product_parser import parse_products
        products = await parse_products([])
        assert products == []

    @pytest.mark.asyncio
    async def test_parse_skips_malformed(self):
        """Malformed product entries should be skipped."""
        mock_response = {
            "products": [
                {
                    "product_name": "Good Product",
                    "brand": "Test",
                    "price": 50.0,
                    "purchase_url": "https://example.com",
                },
                {
                    "product_name": "Bad Product",
                    "price": "not_a_number",  # Should cause parse error
                },
            ]
        }

        with patch("src.discovery.product_parser.call_llm", new_callable=AsyncMock, return_value=mock_response):
            from src.discovery.product_parser import parse_products
            products = await parse_products(["raw text"])

        # At least the good product should parse
        assert len(products) >= 1
