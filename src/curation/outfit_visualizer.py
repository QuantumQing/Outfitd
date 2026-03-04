"""Pure-Python SVG outfit silhouette generator.

Generates a simple male figure avatar (160x300 px) with colored garments
and style-specific collar/neckline/bottom details.
No external dependencies required.
"""

# Color name → hex mapping
COLOR_MAP: dict[str, str] = {
    # Blues
    "navy": "#1a2744", "navy blue": "#1a2744", "blue": "#3a6bc4",
    "light blue": "#6fa3d4", "sky blue": "#87ceeb", "royal blue": "#2d5fb5",
    "cobalt": "#1a52a8", "slate blue": "#4a6fa5",
    # Greens
    "olive": "#6b7c3d", "olive green": "#6b7c3d", "green": "#3a7a3a",
    "dark green": "#1e4d1e", "forest green": "#228b22", "sage": "#9aab7a",
    "army green": "#4b5320", "hunter green": "#355e3b",
    # Browns / Tans
    "tan": "#c9a96e", "khaki": "#c3a96e", "beige": "#d4c5a0",
    "cream": "#f5f0dc", "camel": "#c69b5a", "brown": "#8b5e3c",
    "dark brown": "#5c3317", "rust": "#b7410e", "cognac": "#9a4722",
    # Greys
    "grey": "#6b6b6b", "gray": "#6b6b6b", "charcoal": "#3c3c3c",
    "light grey": "#a8a8a8", "light gray": "#a8a8a8",
    "heather grey": "#9a9a9a", "heather gray": "#9a9a9a", "slate": "#708090",
    # Whites / Blacks
    "white": "#f5f5f0", "off white": "#f0ede5", "ivory": "#fffff0",
    "ecru": "#f0ead6", "oatmeal": "#e8dcc8", "black": "#1c1c1c",
    # Reds / Pinks
    "red": "#c0392b", "burgundy": "#6d1f2e", "maroon": "#6d1f2e",
    "wine": "#7b2d42", "crimson": "#a41e2d", "pink": "#e8a0a0", "rose": "#c77b8a",
    # Yellows / Oranges
    "yellow": "#d4a017", "mustard": "#c9a227", "orange": "#d4622a",
    "copper": "#b87333",
    # Purples
    "purple": "#6a3fa5", "lavender": "#a89bc4", "violet": "#7a3fac",
    # Neutrals / Special
    "stone": "#c1b49a", "sand": "#c9b88a", "denim": "#3a5a8c",
    "indigo": "#2e3f8c", "chambray": "#6a8fb5", "teal": "#006d77",
    "turquoise": "#40b4b4", "cedar": "#a0522d", "amber": "#c9880a",
}

SKIN_TONE = "#c8956c"
SKIN_SHADOW = "#b07d56"


import re

def _color_from_name(color_str: str, default: str = "#888888") -> str:
    """Resolve a color name or partial match to a hex string."""
    if not color_str:
        return default
    c = color_str.lower().strip()
    if c in COLOR_MAP:
        return COLOR_MAP[c]
    
    # Sort keys by length descending to match 'dark green' before 'green'
    for key in sorted(COLOR_MAP.keys(), key=len, reverse=True):
        if re.search(r'\b' + re.escape(key) + r'\b', c):
            return COLOR_MAP[key]
            
    return default


def _darken(hex_color: str, factor: float = 0.75) -> str:
    """Return a slightly darker shade of a hex color for stroke lines."""
    try:
        h = hex_color.lstrip("#")
        if len(h) != 6:
            return hex_color
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"#{max(0,int(r*factor)):02x}{max(0,int(g*factor)):02x}{max(0,int(b*factor)):02x}"
    except Exception:
        return hex_color


def _detect_top_style(name: str) -> str:
    """Return a top style key from a product name."""
    n = name.lower()
    if any(k in n for k in ["hoodie", "hooded sweatshirt", "zip-up", "zip up"]):
        return "hoodie"
    if any(k in n for k in ["polo", "polo shirt"]):
        return "polo"
    if any(k in n for k in ["button", "oxford", "poplin", "flannel shirt", "plaid", "linen shirt", "woven"]):
        return "button_down"
    if "henley" in n:
        return "henley"
    if any(k in n for k in ["crewneck", "crew neck", "crew-neck", "pullover", "sweater", "sweatshirt"]):
        return "crew_neck"
    return "tshirt"


def _detect_bottom_style(name: str) -> str:
    """Return a bottom style key from a product name."""
    n = name.lower()
    if any(k in n for k in ["short", "board short", "swim"]):
        return "shorts"
    if any(k in n for k in ["chino", "trouser", "dress pant", "slacks", "khaki pant"]):
        return "chino"
    return "jeans"


def generate_outfit_svg(outfit_items: list) -> str:
    """Generate a 160×300 px inline SVG silhouette for an outfit."""
    # Neutral-looking defaults that read as "unknown clothing" rather than flat grey
    TOP_DEFAULT = "#7a8fa6"      # steel blue — generic shirt tone
    BOTTOM_DEFAULT = "#2c3e50"   # dark navy — generic trouser/jean tone

    top_color = TOP_DEFAULT
    top_name = ""
    bottom_color = BOTTOM_DEFAULT
    bottom_name = ""
    outer_color = None
    has_belt = False

    for item in outfit_items:
        cat = getattr(item, "category", "").lower()
        color = getattr(item, "color", "") or ""
        pname = getattr(item, "product_name", "") or ""
        note = getattr(item, "stylist_note", "") or ""
        
        c_str = color
        if not c_str:
            c_str = pname + " " + note
            
        if cat == "top":
            top_color = _color_from_name(c_str, default=TOP_DEFAULT)
            top_name = pname
        elif cat == "bottom":
            bottom_color = _color_from_name(c_str, default=BOTTOM_DEFAULT)
            bottom_name = pname
        elif cat == "outerwear":
            outer_color = _color_from_name(c_str)
        elif cat == "belt":
            has_belt = True

    top_style = _detect_top_style(top_name)
    bottom_style = _detect_bottom_style(bottom_name)

    # ── Layout constants ────────────────────────────────────────────────────
    W, H = 160, 300
    cx = 80  # horizontal center

    head_cy, head_r = 36, 22
    neck_x, neck_y, neck_w, neck_h = 73, 56, 14, 16

    torso_x, torso_y, torso_w, torso_h = 44, 72, 72, 80
    torso_cx = torso_x + torso_w // 2  # = 80

    belt_y = torso_y + torso_h       # 152
    belt_h = 7

    leg_w = 28
    left_leg_x = 46
    right_leg_x = 86
    leg_y = belt_y + belt_h          # 159
    leg_h = 55 if bottom_style == "shorts" else 100

    arm_w = 16
    left_arm_x = torso_x - arm_w + 2   # 30
    right_arm_x = torso_x + torso_w - 2  # 114
    arm_y = torso_y + 4
    arm_h = 55

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" style="display:block;">'
    ]

    # ── Hoodie: draw hood BEHIND head ───────────────────────────────────────
    if top_style == "hoodie":
        arm_fill = outer_color if outer_color else top_color
        parts.append(
            f'<ellipse cx="{cx}" cy="{neck_y - 4}" rx="26" ry="22" '
            f'fill="{top_color}" stroke="{_darken(top_color)}" stroke-width="1.5"/>'
        )

    # ── Head ────────────────────────────────────────────────────────────────
    parts.append(
        f'<circle cx="{cx}" cy="{head_cy}" r="{head_r}" '
        f'fill="{SKIN_TONE}" stroke="{SKIN_SHADOW}" stroke-width="1.5"/>'
    )

    # ── Neck ────────────────────────────────────────────────────────────────
    parts.append(
        f'<rect x="{neck_x}" y="{neck_y}" width="{neck_w}" height="{neck_h}" '
        f'fill="{SKIN_TONE}"/>'
    )

    # ── Arms ────────────────────────────────────────────────────────────────
    arm_fill = outer_color if outer_color else top_color
    for ax in [left_arm_x, right_arm_x]:
        parts.append(
            f'<rect x="{ax}" y="{arm_y}" width="{arm_w}" height="{arm_h}" rx="7" '
            f'fill="{arm_fill}" stroke="{_darken(arm_fill)}" stroke-width="1"/>'
        )

    # ── Torso / shirt ───────────────────────────────────────────────────────
    parts.append(
        f'<rect x="{torso_x}" y="{torso_y}" width="{torso_w}" height="{torso_h}" rx="4" '
        f'fill="{top_color}" stroke="{_darken(top_color)}" stroke-width="1.5"/>'
    )

    # ── Outerwear overlay (open-front lapel) ────────────────────────────────
    if outer_color:
        lapel_w = int(torso_w * 0.42)
        for lx in [torso_x, torso_x + torso_w - lapel_w]:
            parts.append(
                f'<rect x="{lx}" y="{torso_y}" width="{lapel_w}" height="{torso_h}" rx="3" '
                f'fill="{outer_color}" opacity="0.92" stroke="{_darken(outer_color)}" stroke-width="1"/>'
            )

    # ── Collar / neckline details ────────────────────────────────────────────
    if top_style == "polo":
        # Two small collar flaps + short button placket
        parts.append(
            f'<polygon points="{cx-2},{torso_y} {cx-14},{torso_y-4} {cx-8},{torso_y+12}" '
            f'fill="{top_color}" stroke="{_darken(top_color)}" stroke-width="1.2"/>'
        )
        parts.append(
            f'<polygon points="{cx+2},{torso_y} {cx+14},{torso_y-4} {cx+8},{torso_y+12}" '
            f'fill="{top_color}" stroke="{_darken(top_color)}" stroke-width="1.2"/>'
        )
        parts.append(
            f'<line x1="{cx}" y1="{torso_y}" x2="{cx}" y2="{torso_y+22}" '
            f'stroke="{_darken(top_color)}" stroke-width="1.5"/>'
        )
        for by in [torso_y + 8, torso_y + 17]:
            parts.append(f'<circle cx="{cx}" cy="{by}" r="1.8" fill="{_darken(top_color)}"/>')

    elif top_style == "button_down":
        # Pointed shirt collar (left + right)
        parts.append(
            f'<polygon points="{cx-2},{torso_y} {cx-18},{torso_y-3} {cx-10},{torso_y+16}" '
            f'fill="{top_color}" stroke="{_darken(top_color)}" stroke-width="1.2"/>'
        )
        parts.append(
            f'<polygon points="{cx+2},{torso_y} {cx+18},{torso_y-3} {cx+10},{torso_y+16}" '
            f'fill="{top_color}" stroke="{_darken(top_color)}" stroke-width="1.2"/>'
        )
        # Full-length button placket
        parts.append(
            f'<line x1="{cx}" y1="{torso_y}" x2="{cx}" y2="{torso_y + torso_h}" '
            f'stroke="{_darken(top_color)}" stroke-width="1" opacity="0.7"/>'
        )
        for k in range(5):
            by = torso_y + 10 + k * 14
            parts.append(f'<circle cx="{cx}" cy="{by}" r="1.5" fill="{_darken(top_color)}"/>')

    elif top_style == "henley":
        # Round neckline cutout + short placket with 3 buttons
        parts.append(
            f'<ellipse cx="{cx}" cy="{torso_y}" rx="9" ry="5" fill="{SKIN_TONE}"/>'
        )
        parts.append(
            f'<line x1="{cx}" y1="{torso_y+5}" x2="{cx}" y2="{torso_y+24}" '
            f'stroke="{_darken(top_color)}" stroke-width="1.5"/>'
        )
        for by in [torso_y + 9, torso_y + 16, torso_y + 23]:
            parts.append(f'<circle cx="{cx}" cy="{by}" r="1.5" fill="{_darken(top_color)}"/>')

    elif top_style == "hoodie":
        # Kangaroo pocket + center seam
        parts.append(
            f'<rect x="{cx-14}" y="{torso_y+42}" width="28" height="20" '
            f'rx="3" fill="{_darken(top_color)}" opacity="0.35"/>'
        )
        parts.append(
            f'<line x1="{cx}" y1="{torso_y}" x2="{cx}" y2="{torso_y+torso_h}" '
            f'stroke="{_darken(top_color)}" stroke-width="1" opacity="0.4"/>'
        )

    else:
        # T-shirt / crew neck: simple oval neckline in skin tone
        parts.append(
            f'<ellipse cx="{cx}" cy="{torso_y}" rx="10" ry="5" fill="{SKIN_TONE}"/>'
        )

    # ── Belt ────────────────────────────────────────────────────────────────
    if has_belt:
        parts.append(
            f'<rect x="{torso_x}" y="{belt_y}" width="{torso_w}" height="{belt_h}" '
            f'fill="#6b4423" rx="2"/>'
        )
        buckle_x = torso_x + torso_w // 2 - 6
        parts.append(
            f'<rect x="{buckle_x}" y="{belt_y+1}" width="12" height="{belt_h-2}" '
            f'fill="#c8a742" rx="1"/>'
        )

    # ── Legs ────────────────────────────────────────────────────────────────
    for lx in [left_leg_x, right_leg_x]:
        parts.append(
            f'<rect x="{lx}" y="{leg_y}" width="{leg_w}" height="{leg_h}" rx="5" '
            f'fill="{bottom_color}" stroke="{_darken(bottom_color)}" stroke-width="1.5"/>'
        )

    # Bottom style details
    if bottom_style == "jeans":
        # Subtle seam line down each leg
        for lx in [left_leg_x, right_leg_x]:
            seam_x = lx + leg_w // 2
            parts.append(
                f'<line x1="{seam_x}" y1="{leg_y+4}" x2="{seam_x}" y2="{leg_y+leg_h-4}" '
                f'stroke="{_darken(bottom_color, 0.65)}" stroke-width="1" opacity="0.5"/>'
            )
    elif bottom_style == "chino":
        # Centre crease line
        for lx in [left_leg_x, right_leg_x]:
            crease_x = lx + leg_w // 2
            parts.append(
                f'<line x1="{crease_x}" y1="{leg_y}" x2="{crease_x}" y2="{leg_y+leg_h}" '
                f'stroke="{_darken(bottom_color, 0.7)}" stroke-width="0.8" opacity="0.6"/>'
            )

    # ── Feet ────────────────────────────────────────────────────────────────
    foot_y = leg_y + leg_h
    for lx in [left_leg_x, right_leg_x]:
        parts.append(
            f'<ellipse cx="{lx + leg_w//2}" cy="{foot_y + 7}" '
            f'rx="{leg_w//2 + 3}" ry="7" fill="#555566" opacity="0.5"/>'
        )

    parts.append("</svg>")
    return "\n".join(parts)
