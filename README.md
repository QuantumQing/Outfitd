# Outfitd: Personal AI-Powered Clothing Subscription System

Outfitd is a self-hosted, AI-powered personal styling system that replaces the human stylist with an LLM and real-time product search. It curates personalized monthly "trunks" (outfit recommendations) directly from online retailers, learns your tastes over time, and gets smarter with every keep, skip, and return.

Inspired by — and intended to replace — services like Trunk Club and Stitch Fix, but running entirely on your own infrastructure.

---

<img width="2752" height="1536" alt="outfitd" src="https://github.com/user-attachments/assets/bc343e59-8010-46ab-a58b-297835fd297a" />

---

## Features

### Core Styling Pipeline

- **Phase 1 — Briefing:** Generates a natural-language stylist brief from your profile, body measurements, seasonal context, and accumulated preference weights.
- **Phase 2 — Sourcing:** Queries the Serper.dev Google Shopping API for real-time prices, purchase URLs, and product images from real retailers.
- **Phase 3 — Assembly:** An LLM (via OpenRouter) assembles coherent outfits (top + bottom + optional outerwear), enforcing color contrast, formality tiering, and your fit/size rules.

### Continuous Style Learning

- Every keep, skip, or return from your trunk updates weighted signals across brand, color, article type, and category dimensions.
- The Discovery feed's like/dislike interface feeds into the same `style_learning` table.
- After ~10 likes, the discovery feed shifts to ~70% personalized queries — surfacing items that match your exact taste profile.

### Discovery Feed

- A swipe-style (like/dislike) feed of individual items outside the monthly trunk cycle.
- Dynamically balances exploratory (brand-new) and personalized results based on your feedback history.
- Uses LLM-generated, persona-aware search queries to avoid staleness and brand repetition.

### Shoe Recommendations

- Generates palette-matched shoe recommendations derived from the dominant colors in your latest trunk.
- LLM produces diverse queries (sneakers, Chelsea boots, athletic shoes, casual loafers) tuned to your persona's aesthetic and lifestyle.
- Results are cached per trunk for instant page loads on return visits.

### Deep Personalization via `user_persona.md`

- A plaintext Markdown file at the project root that encodes your body type, fit logic, exact sizing, style dealbreakers, and brand preferences.
- This document is injected as a hard override into every LLM prompt across the entire pipeline (briefing, discovery, shoes).
- Lets you capture nuanced fit rules that can't be expressed in a simple UI — for example: *"never recommend slim-fit jeans without stretch fabric; I have athletic thighs."*

### Wildcard Outfits

- Every trunk intentionally includes one outfit outside your normal style profile to encourage discovery and break pattern ruts.

### Automated Scheduling

- APScheduler triggers trunk generation on the first of each month and runs a daily retention check.
- Fully hands-off once configured.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python) |
| Database | SQLite (zero config, single file) |
| Frontend | Jinja2 templates + Pico CSS (server-rendered, no JS build tools) |
| Product Discovery | Serper.dev Google Shopping API |
| LLM Reasoning | OpenRouter (DeepSeek V3, Claude Haiku, or any compatible model) |
| Scheduling | APScheduler (embedded in the FastAPI process) |
| Deployment | Docker / Docker Compose |

---

## Quick Start

### 1. Prerequisites

- Docker & Docker Compose
- A [Serper.dev](https://serper.dev) API key (Google Shopping product search)
- An [OpenRouter](https://openrouter.ai) API key (LLM curation)
- Optional: [Perplexity](https://docs.perplexity.ai) API key (alternate product sourcing path)

### 2. Configure API Keys

```bash
git clone https://github.com/QuantumQing/Outfitd.git
cd Outfitd
cp .env.example .env
```

Edit `.env` with your keys:

```env
SERPER_API_KEY="your_key_here"
OPENROUTER_API_KEY="your_key_here"
OPENROUTER_MODEL="deepseek/deepseek-chat-v3-0324"

# Optional
PERPLEXITY_API_KEY="your_key_here"
```

### 3. Set Up Your Persona

Copy the example persona and customize it with your own body measurements, fit preferences, and style rules:

```bash
cp user_persona.md.example user_persona.md
```

Edit `user_persona.md` — this single file powers every AI decision in the system. The more detail you add, the better the recommendations. See the example file for structure guidance.

> `user_persona.md` is gitignored so your personal measurements never get committed.

### 4. Run

```bash
# Start the app
docker-compose up -d --build

# First time: initialize the database
docker-compose exec outfitd python scripts/init_db.py

# Manually trigger a trunk generation
docker-compose exec outfitd python scripts/generate_trunk.py
```

**Local development (no Docker):**

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.main:app --reload
```

---

## How It Works

```
user_persona.md + UI Profile
         │
         ▼
[Phase 1: Stylist Brief]
LLM generates a natural-language brief
factoring in season, learned weights, persona
         │
         ▼
[Phase 2: Product Discovery]
Serper.dev Google Shopping queries
→ real retailer URLs, prices, images
         │
         ▼
[Phase 3: Outfit Assembly]
LLM assembles coherent outfits
enforcing: color contrast, size fit, vibe
         │
         ▼
[Trunk Web UI]
Review → Keep / Skip / Return
Feedback → updates style_learning weights
         │
         ▼
[Next Month: Better Recommendations]
```

---

## Utility Scripts

| Script | Purpose |
|---|---|
| `scripts/init_db.py` | Initialize the SQLite database schema |
| `scripts/generate_trunk.py` | Manually trigger a full trunk generation |
| `scripts/clear_discovery_cache.py` | Clear unvoted discovery items from the DB to refresh the feed |
| `scripts/dump_items.py` | Dump all trunk items to JSON for debugging |
| `scripts/repair_trunk.py` | Attempt to repair a broken or incomplete trunk |

---

## Project Structure

```
outfitd/
├── src/
│   ├── main.py              # FastAPI entry point, lifespan, router registration
│   ├── config.py            # Pydantic settings from .env
│   ├── database.py          # SQLite connection helper
│   ├── models.py            # Pydantic data models
│   ├── curation/            # LLM briefing, outfit assembly, visualizer
│   ├── discovery/           # Trending feed, brand discovery, Serper integration
│   ├── feedback/            # Keep/skip/return signal handlers
│   ├── profile/             # User profile CRUD
│   ├── shoes/               # Palette-matched shoe recommendations
│   ├── trunk/               # Trunk generation pipeline + APScheduler
│   ├── templates/           # Jinja2 HTML templates
│   └── static/              # CSS, JS, uploaded images
├── scripts/                 # Utility scripts (init, generate, repair, clear)
├── data/                    # SQLite database (gitignored)
├── user_persona.md          # Your personal fit/style rules (gitignored)
├── user_persona.md.example  # Template to get started
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

---

## Roadmap / Premium Upgrades

See [`PREMIUM_UPGRADES.md`](PREMIUM_UPGRADES.md) for the next tier of product accuracy:
- Real-time size in-stock verification via Firecrawl / Browserbase
- Per-SKU data extraction with return policy parsing
- SerpApi Google Shopping as a higher-fidelity discovery layer
- Affiliate catalog API integrations (CJ, Rakuten)

Estimated cost at the premium tier: ~$0.50–$1.20 per trunk generation.

---

## Contributing

Pull requests welcome. The architecture is intentionally simple: pure Python, SQLite, server-rendered HTML. No frontend build tooling, no ORMs, no microservices.
