"""Feedback routes — API endpoint for item decisions."""

from fastapi import APIRouter, HTTPException

from src.feedback.service import record_decision, record_return, record_keep
from src.feedback.learner import get_all_weights

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.get("/weights")
async def get_weights():
    """Get all learned style weights."""
    return {"weights": get_all_weights()}
