"""
utils.py
--------
Small shared helpers: saving uploaded images, formatting numbers, etc.
"""

from pathlib import Path
from datetime import datetime
from PIL import Image

IMAGES_DIR = Path(__file__).parent / "data" / "meal_images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def save_meal_image(image: Image.Image, log_date: str) -> str:
    """Save a copy of the meal photo locally and return its relative path."""
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"{log_date}_{timestamp}.jpg"
    path = IMAGES_DIR / filename
    image.convert("RGB").save(path, format="JPEG", quality=80)
    return str(path)


def fmt(value, unit="", decimals=0):
    """Format a number nicely for display, or return '—' if missing."""
    if value is None:
        return "—"
    try:
        if decimals == 0:
            return f"{value:,.0f}{unit}"
        return f"{value:,.{decimals}f}{unit}"
    except (TypeError, ValueError):
        return "—"


def macro_bar_pct(current, target):
    """Return a 0-100 percentage for progress bars, clamped."""
    if not target or target <= 0:
        return 0
    pct = (current / target) * 100
    return max(0, min(100, pct))
