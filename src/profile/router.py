"""Profile routes — GET/PUT /profile with HTML form and API endpoints."""

import os
import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.profile.service import get_profile, update_profile

router = APIRouter(prefix="/profile", tags=["profile"])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("", response_class=HTMLResponse)
async def profile_page(request: Request):
    """Render the profile editor form."""
    profile = get_profile()
    return templates.TemplateResponse(
        "profile.html",
        {"request": request, "profile": profile, "page_title": "Style Profile"},
    )


@router.post("")
async def update_profile_form(
    request: Request,
    height: str = Form(""),
    skin_color: str = Form(""),
    fit_preference: str = Form("regular"),
    bottom_fit: str = Form("slim"),
    bottom_rise: str = Form("low"),
    occasion: str = Form("casual"),
    style_notes: str = Form(""),
    dislikes: str = Form(""),
    budget_min: float = Form(40.0),
    budget_max: float = Form(120.0),
    budget_tops: float = Form(0.0),
    budget_bottoms: float = Form(0.0),
    budget_outerwear: float = Form(0.0),
    budget_shoes: float = Form(0.0),
    brands_liked: str = Form(""),
    colors_preferred: str = Form(""),
    chest: str = Form(""),
    waist: str = Form(""),
    inseam: str = Form(""),
    neck: str = Form(""),
    shoulder_width: str = Form(""),
    shoe_size: str = Form(""),
    shirt_size: str = Form(""),
    pants_size: str = Form(""),
    shoe_size_val: str = Form(""),
    photo: UploadFile = File(None),
):
    """Handle profile form submission."""
    data = {
        "height": height,
        "skin_color": skin_color,
        "fit_preference": fit_preference,
        "bottom_fit": bottom_fit,
        "bottom_rise": bottom_rise,
        "occasion": occasion,
        "style_notes": style_notes,
        "dislikes": [d.strip() for d in dislikes.split(",") if d.strip()],
        "budget_min": budget_min,
        "budget_max": budget_max,
        "budget_per_category": {
            "tops": budget_tops,
            "bottoms": budget_bottoms,
            "outerwear": budget_outerwear,
            "shoes": budget_shoes,
        },
        "brands_liked": [b.strip() for b in brands_liked.split(",") if b.strip()],
        "colors_preferred": [c.strip() for c in colors_preferred.split(",") if c.strip()],
        "measurements": {
            "chest": chest,
            "waist": waist,
            "inseam": inseam,
            "neck": neck,
            "shoulder_width": shoulder_width,
            "shoe_size": shoe_size,
        },
        "sizes": {
            "shirt": shirt_size,
            "pants": pants_size,
            "shoe": shoe_size_val,
        },
    }

    # Handle photo upload
    if photo and photo.filename:
        ext = Path(photo.filename).suffix
        photo_path = UPLOAD_DIR / f"profile_photo{ext}"
        with open(photo_path, "wb") as f:
            shutil.copyfileobj(photo.file, f)
        data["photo_path"] = str(photo_path)

    update_profile(data)
    return RedirectResponse(url="/profile", status_code=303)


@router.get("/api", response_model=None)
async def get_profile_api():
    """API endpoint: return profile as JSON."""
    profile = get_profile()
    return profile.model_dump()


@router.put("/api")
async def update_profile_api(request: Request):
    """API endpoint: update profile from JSON body."""
    body = await request.json()
    profile = update_profile(body)
    return profile.model_dump()
