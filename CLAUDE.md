# Outfitd Developer Notes

## Architecture

- **Entry point:** `src/main.py` — FastAPI app with lifespan startup (DB init + APScheduler)
- **Database:** `data/trunk.db` (SQLite). Schema initialized via `scripts/init_db.py`
- **Templates:** `src/templates/` (Jinja2) + `src/static/` (Pico CSS, minimal JS)

## Key Modules

| Module | Path | Purpose |
|---|---|---|
| Profile | `src/profile/` | User profile CRUD (measurements, sizes, preferences) |
| Trunk | `src/trunk/` | Monthly outfit generation pipeline + APScheduler |
| Curation | `src/curation/` | LLM stylist brief, outfit assembly, visualizer |
| Discovery | `src/discovery/` | Serper shopping search, trending/personalized feed |
| Feedback | `src/feedback/` | Keep/skip/return signal handlers |
| Shoes | `src/shoes/` | Palette-matched shoe recommendations |

## Persona System

`user_persona.md` (project root) is injected into every LLM prompt as a hard-override layer. It contains the user's body measurements, fit logic, brand preferences, and style dealbreakers. It is gitignored so users can store personal data without risk of committing it. See `user_persona.md.example` for the expected structure.

## Style Learning

User feedback writes weighted signals to the `style_learning` table in SQLite. Dimensions tracked: `brand`, `color`, `article_type`, `category`. These weights are consumed by `src/discovery/service.py` to personalize the discovery feed over time.

## Scripts

- `scripts/init_db.py` — initialize schema (safe to re-run; uses `CREATE TABLE IF NOT EXISTS`)
- `scripts/generate_trunk.py` — trigger a full trunk generation outside the scheduler
- `scripts/clear_discovery_cache.py` — delete unvoted discovery items to force a fresh feed
- `scripts/dump_items.py` — dump trunk items to JSON for inspection
- `scripts/repair_trunk.py` — repair a broken or partial trunk

## Environment Variables

See `.env.example` for all supported variables. Minimum required to run:

```
SERPER_API_KEY
OPENROUTER_API_KEY
```
