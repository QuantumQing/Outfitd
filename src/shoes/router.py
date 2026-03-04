"""Shoes router — GET /shoes renders shoe recommendations."""

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.shoes.service import generate_shoe_recommendations

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shoes", tags=["shoes"])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("", response_class=HTMLResponse)
async def shoes_page(request: Request):
    """Render shoe recommendations based on the latest trunk's palette."""
    try:
        shoes = await generate_shoe_recommendations()
    except Exception as e:
        logger.error(f"Shoe recommendations failed: {e}", exc_info=True)
        shoes = []

    return templates.TemplateResponse(
        "shoes.html",
        {
            "request": request,
            "shoes": shoes,
            "page_title": "Shoe Pairings",
        },
    )
