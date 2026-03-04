"""SQLite database setup — schema creation and connection management."""

import sqlite3
import os
from pathlib import Path
from contextlib import contextmanager

from src.config import settings

# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY DEFAULT 1,
    height TEXT DEFAULT '',
    skin_color TEXT DEFAULT '',
    photo_path TEXT DEFAULT '',
    measurements TEXT DEFAULT '{}',       -- JSON: chest, waist, inseam, neck, shoulder, shoe_size
    sizes TEXT DEFAULT '{}',              -- JSON: shirt, pants, shoe (brand-keyed)
    brands_liked TEXT DEFAULT '[]',       -- JSON array
    budget_min REAL DEFAULT 40.0,
    budget_max REAL DEFAULT 120.0,
    colors_preferred TEXT DEFAULT '[]',   -- JSON array
    fit_preference TEXT DEFAULT 'regular',
    occasion TEXT DEFAULT 'casual',
    style_notes TEXT DEFAULT '',
    dislikes TEXT DEFAULT '[]',           -- JSON array of disliked items/styles
    budget_per_category TEXT DEFAULT '{}', -- JSON: {tops, bottoms, outerwear, accessories}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trunk (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    season TEXT NOT NULL,
    stylist_brief TEXT DEFAULT '',
    status TEXT DEFAULT 'pending'          -- pending | reviewed | archived
);

CREATE TABLE IF NOT EXISTS trunk_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trunk_id INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    brand TEXT DEFAULT '',
    category TEXT DEFAULT '',              -- top, bottom, outerwear, shoes, belt, accessory
    color TEXT DEFAULT '',
    size TEXT DEFAULT '',
    price REAL DEFAULT 0.0,
    retailer TEXT DEFAULT '',
    purchase_url TEXT DEFAULT '',
    image_url TEXT DEFAULT '',
    return_policy_days INTEGER DEFAULT 30,
    return_policy_summary TEXT DEFAULT '',
    outfit_group INTEGER DEFAULT 0,        -- items with same number form an outfit
    is_wildcard INTEGER DEFAULT 0,         -- 1 = wildcard outfit item
    decision TEXT DEFAULT '',              -- purchase | skip | dislike
    returned INTEGER DEFAULT 0,            -- 1 = returned after purchase
    stylist_note TEXT DEFAULT '',
    outfit_description TEXT DEFAULT '',
    feedback_reason TEXT DEFAULT '',       -- Color | Style | Article
    feedback_text TEXT DEFAULT '',         -- User context
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trunk_id) REFERENCES trunk(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trunk_item_id INTEGER NOT NULL,
    action TEXT NOT NULL,                  -- skip | purchase | return | keep | dislike
    signal_strength REAL NOT NULL,         -- -0.5, +0.5, -0.3, +1.0, -1.0
    reason TEXT DEFAULT '',                -- reason text
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trunk_item_id) REFERENCES trunk_item(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS style_learning (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dimension TEXT NOT NULL,               -- brand | color | category | fit | price_range
    value TEXT NOT NULL,                   -- e.g. "J.Crew", "navy", "chinos"
    weight REAL DEFAULT 0.0,              -- cumulative preference weight
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(dimension, value)
);
CREATE TABLE IF NOT EXISTS discovery_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    brand TEXT NOT NULL,
    category TEXT DEFAULT '',
    color TEXT DEFAULT '',
    article_type TEXT DEFAULT '',          -- polo, jeans, chinos, henley, etc.
    image_url TEXT NOT NULL,
    purchase_url TEXT DEFAULT '',
    price REAL DEFAULT 0.0,
    decision TEXT DEFAULT NULL,            -- 'like' | 'dislike' | 'skip'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(product_name, brand)
);
"""


def get_db_path() -> str:
    """Return the resolved database file path."""
    return settings.db_path


def ensure_db_dir():
    """Create the database directory if it doesn't exist."""
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)


def _migrate_schema():
    """Add missing columns to existing tables."""
    conn = sqlite3.connect(get_db_path())
    try:
        # Check user_profile
        cursor = conn.execute("PRAGMA table_info(user_profile)")
        columns = [row[1] for row in cursor.fetchall()]
        if "dislikes" not in columns:
            conn.execute("ALTER TABLE user_profile ADD COLUMN dislikes TEXT DEFAULT '[]'")
        if "budget_per_category" not in columns:
            conn.execute("ALTER TABLE user_profile ADD COLUMN budget_per_category TEXT DEFAULT '{}'")
        if "bottom_fit" not in columns:
            conn.execute("ALTER TABLE user_profile ADD COLUMN bottom_fit TEXT DEFAULT 'slim'")
        if "bottom_rise" not in columns:
            conn.execute("ALTER TABLE user_profile ADD COLUMN bottom_rise TEXT DEFAULT 'low'")

        # Check trunk_item
        cursor = conn.execute("PRAGMA table_info(trunk_item)")
        columns = [row[1] for row in cursor.fetchall()]
        if "feedback_reason" not in columns:
            conn.execute("ALTER TABLE trunk_item ADD COLUMN feedback_reason TEXT DEFAULT ''")
        if "feedback_text" not in columns:
            conn.execute("ALTER TABLE trunk_item ADD COLUMN feedback_text TEXT DEFAULT ''")
        if "outfit_description" not in columns:
            conn.execute("ALTER TABLE trunk_item ADD COLUMN outfit_description TEXT DEFAULT ''")
        if "return_policy_summary" not in columns:
            conn.execute("ALTER TABLE trunk_item ADD COLUMN return_policy_summary TEXT DEFAULT ''")
            
        # Check feedback table (add reason if missing)
        cursor = conn.execute("PRAGMA table_info(feedback)")
        columns = [row[1] for row in cursor.fetchall()]
        if "reason" not in columns:
            conn.execute("ALTER TABLE feedback ADD COLUMN reason TEXT DEFAULT ''")

        # Check discovery_item — add color and article_type if missing
        cursor = conn.execute("PRAGMA table_info(discovery_item)")
        columns = [row[1] for row in cursor.fetchall()]
        if "color" not in columns:
            conn.execute("ALTER TABLE discovery_item ADD COLUMN color TEXT DEFAULT ''")
        if "article_type" not in columns:
            conn.execute("ALTER TABLE discovery_item ADD COLUMN article_type TEXT DEFAULT ''")

        conn.commit()
    except Exception as e:
        print(f"Migration warning: {e}")
    finally:
        conn.close()


def init_db():
    """Create all tables. Safe to call multiple times."""
    ensure_db_dir()
    conn = sqlite3.connect(get_db_path())
    conn.executescript(SCHEMA)
    conn.close()
    
    _migrate_schema()

    # Seed default profile row if it doesn't exist
    conn = sqlite3.connect(get_db_path())
    cursor = conn.execute("SELECT COUNT(*) FROM user_profile")
    if cursor.fetchone()[0] == 0:
        conn.execute("INSERT INTO user_profile (id) VALUES (1)")
        conn.commit()
    conn.close()


@contextmanager
def get_db():
    """Yield a SQLite connection with row_factory set for dict-like access."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
