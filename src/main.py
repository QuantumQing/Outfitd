"""Outfitd — FastAPI entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.database import init_db
from src.profile.router import router as profile_router
from src.trunk.router import router as trunk_router
from src.feedback.router import router as feedback_router
from src.discovery.router import router as discovery_router
from src.shoes.router import router as shoes_router
from src.trunk.scheduler import start_scheduler

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
SRC_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = SRC_DIR / "templates"
STATIC_DIR = SRC_DIR / "static"


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logger.info("Starting Outfitd...")
    init_db()
    start_scheduler()
    logger.info("Outfitd ready")
    yield
    logger.info("Shutting down...")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Outfitd",
    description="Personal AI-Powered Clothing Subscription System",
    version="0.1.0",
    lifespan=lifespan,
)

# Static files
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "uploads").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Routers
app.include_router(profile_router)
app.include_router(trunk_router)
app.include_router(feedback_router)
app.include_router(discovery_router)
app.include_router(shoes_router)


# ── Root ──────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Landing page — redirect to trunk or profile based on state."""
    return RedirectResponse(url="/trunk")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "app": "outfitd", "version": "0.1.0"}
