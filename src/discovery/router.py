import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src.discovery.service import get_discovery_feed, record_discovery_feedback
from src.models import DecisionRequest

router = APIRouter(prefix="/discover", tags=["discover"])

# Match path structure used in main.py
SRC_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = SRC_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

logger = logging.getLogger(__name__)

@router.get("/", response_class=HTMLResponse)
async def discover_page(request: Request):
    """Render the discovery swipe UI."""
    return templates.TemplateResponse("discover.html", {"request": request})

@router.get("/feed")
async def get_feed():
    """Get a batch of discovery items."""
    try:
        items = await get_discovery_feed(limit=10)
        return items
    except Exception as e:
        logger.error(f"Feed error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch feed")

@router.post("/feedback/{item_id}")
async def submit_feedback(item_id: int, payload: DecisionRequest):
    """Record like/dislike."""
    # We reuse DecisionRequest but expect 'like' or 'dislike' here
    if payload.decision not in ("like", "dislike"):
        raise HTTPException(status_code=400, detail="Invalid decision. Must be 'like' or 'dislike'.")
        
    try:
        record_discovery_feedback(item_id, payload.decision)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Feedback error: {e}")
        raise HTTPException(status_code=500, detail="Failed to record feedback")
