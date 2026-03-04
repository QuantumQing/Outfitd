"""Profile CRUD operations against SQLite."""

import json
from src.database import get_db
from src.models import UserProfile, Measurements, Sizes, CategoryBudget


def get_profile() -> UserProfile:
    """Load the single user profile from the database."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
        if not row:
            return UserProfile()

        return UserProfile(
            id=row["id"],
            height=row["height"] or "",
            skin_color=row["skin_color"] or "",
            photo_path=row["photo_path"] or "",
            measurements=Measurements(**json.loads(row["measurements"] or "{}")),
            sizes=Sizes(**json.loads(row["sizes"] or "{}")),
            brands_liked=json.loads(row["brands_liked"] or "[]"),
            budget_min=row["budget_min"] or 40.0,
            budget_max=row["budget_max"] or 120.0,
            colors_preferred=json.loads(row["colors_preferred"] or "[]"),
            fit_preference=row["fit_preference"] or "regular",
            bottom_fit=row["bottom_fit"] or "slim",
            bottom_rise=row["bottom_rise"] or "low",
            occasion=row["occasion"] or "casual",
            style_notes=row["style_notes"] or "",
            dislikes=json.loads(row["dislikes"] or "[]"),
            budget_per_category=CategoryBudget(**json.loads(row["budget_per_category"] or "{}")),
        )


def update_profile(data: dict) -> UserProfile:
    """Update profile fields. Accepts partial updates."""
    # Build SET clause dynamically
    set_parts = []
    values = []

    field_map = {
        "height": "height",
        "skin_color": "skin_color",
        "photo_path": "photo_path",
        "budget_min": "budget_min",
        "budget_max": "budget_max",
        "fit_preference": "fit_preference",
        "bottom_fit": "bottom_fit",
        "bottom_rise": "bottom_rise",
        "occasion": "occasion",
        "style_notes": "style_notes",
    }

    # Simple string/numeric fields
    for key, col in field_map.items():
        if key in data and data[key] is not None:
            set_parts.append(f"{col} = ?")
            values.append(data[key])

    # JSON fields
    json_fields = {
        "measurements": "measurements",
        "sizes": "sizes",
        "brands_liked": "brands_liked",
        "colors_preferred": "colors_preferred",
        "dislikes": "dislikes",
        "budget_per_category": "budget_per_category",
    }

    for key, col in json_fields.items():
        if key in data and data[key] is not None:
            val = data[key]
            if isinstance(val, (dict, list)):
                set_parts.append(f"{col} = ?")
                values.append(json.dumps(val))
            elif hasattr(val, "model_dump"):
                set_parts.append(f"{col} = ?")
                values.append(json.dumps(val.model_dump()))

    if set_parts:
        set_parts.append("updated_at = CURRENT_TIMESTAMP")
        query = f"UPDATE user_profile SET {', '.join(set_parts)} WHERE id = 1"
        with get_db() as conn:
            conn.execute(query, values)

    return get_profile()
