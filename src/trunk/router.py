"""Trunk routes — view, generate, and manage trunks."""

import logging
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
import httpx
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.trunk.service import (
    generate_trunk,
    get_trunk,
    get_latest_trunk,
    list_trunks,
    update_item_decision,
    undo_item_decision,
    mark_item_returned,
    record_item_feedback,
    reroll_outfit,
)
from src.models import DecisionRequest, ReturnRequest, FeedbackPayload, RerollRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trunk", tags=["trunk"])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("", response_class=HTMLResponse)
async def trunk_page(request: Request):
    """Show the latest trunk for review."""
    import traceback
    try:
        trunk = get_latest_trunk()
        # Group items by outfit
        outfits = {}
        if trunk:
            for item in trunk.items:
                group = item.outfit_group
                if group not in outfits:
                    outfits[group] = {
                        "items": [],
                        "is_wildcard": item.is_wildcard,
                        "outfit_description": item.outfit_description,
                    }
                outfits[group]["items"].append(item)

        return templates.TemplateResponse(
            "trunk.html",
            {
                "request": request,
                "trunk": trunk,
                "outfits": outfits,
                "page_title": "Your Trunk",
            },
        )
    except Exception as e:
        logger.error(f"Error rendering trunk page: {e}", exc_info=True)
        error_trace = traceback.format_exc()
        # Padding to prevent browser from hiding the error message (some browsers hide < 512 bytes)
        padding = "<!-- " + "x" * 512 + " -->"
        return HTMLResponse(
            content=f"<h1>Internal Server Error</h1><pre>{error_trace}</pre>{padding}",
            status_code=500,
        )


@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    """Show past trunks."""
    trunks = list_trunks()
    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "trunks": trunks,
            "page_title": "Trunk History",
        },
    )


@router.get("/{trunk_id}", response_class=HTMLResponse)
async def trunk_detail_page(request: Request, trunk_id: int):
    """Show a specific trunk."""
    try:
        trunk = get_trunk(trunk_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Trunk not found")

    outfits = {}
    for item in trunk.items:
        group = item.outfit_group
        if group not in outfits:
            outfits[group] = {
                "items": [], 
                "is_wildcard": item.is_wildcard,
                "outfit_description": item.outfit_description,
            }
        outfits[group]["items"].append(item)

    return templates.TemplateResponse(
        "trunk.html",
        {
            "request": request,
            "trunk": trunk,
            "outfits": outfits,
            "page_title": f"Trunk #{trunk_id}",
        },
    )


@router.post("/generate")
async def generate_trunk_api():
    """Trigger trunk generation (API endpoint)."""
    try:
        trunk = await generate_trunk()
        return {"status": "success", "trunk_id": trunk.id}
    except ValueError as e:
        logger.warning(f"Trunk generation validation error: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except httpx.HTTPStatusError as e:
        logger.error(f"External API error: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail="External dependency failed")
    except Exception as e:
        logger.error(f"Trunk generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/{item_id}/decide")
async def decide_item(item_id: int, body: DecisionRequest):
    """Record a purchase/skip decision for a trunk item."""
    try:
        update_item_decision(item_id, body.decision)

        # Trigger feedback recording
        from src.feedback.service import record_decision
        record_decision(item_id, body.decision)

        return {"status": "ok", "item_id": item_id, "decision": body.decision}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{item_id}/undo")
async def undo_decision_api(item_id: int):
    """Undo a decision for an item."""
    try:
        undo_item_decision(item_id)
        return {"status": "success", "item_id": item_id}
    except Exception as e:
        logger.error(f"Undo failed: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/{item_id}/feedback")
async def item_feedback_api(item_id: int, body: FeedbackPayload):
    """Record negative feedback (dislike)."""
    try:
        record_item_feedback(item_id, body.reason, body.text)
        
        # Trigger learner (import inside function to avoid circular dep if any)
        from src.feedback.service import record_dislike
        record_dislike(item_id, body.reason)
        
        return {"status": "success", "item_id": item_id}
    except Exception as e:
        logger.error(f"Feedback failed: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/{item_id}/return")
async def return_item(item_id: int, body: ReturnRequest):
    """Mark an item as returned."""
    try:
        mark_item_returned(item_id)

        from src.feedback.service import record_return
        record_return(item_id)

        return {"status": "ok", "item_id": item_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{trunk_id}/reroll/{outfit_group}")
async def reroll_outfit_api(trunk_id: int, outfit_group: int, body: RerollRequest):
    """Reroll completely unlocked items in a given outfit group."""
    try:
        await reroll_outfit(trunk_id, outfit_group, body.locked_item_ids)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Reroll failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")
