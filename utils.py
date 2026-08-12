"""
utils.py
--------
Small shared helpers: saving uploaded images, formatting numbers, etc.
"""

from pathlib import Path
from datetime import datetime
from PIL import Image
import io
import base64

IMAGES_DIR = Path(__file__).parent / "data" / "meal_images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def save_meal_image(image: Image.Image, log_date: str) -> str:
    """Save a copy of the meal photo locally and return its relative path."""
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"{log_date}_{timestamp}.jpg"
    path = IMAGES_DIR / filename
    image.convert("RGB").save(path, format="JPEG", quality=80)
    return str(path)


def image_to_base64(image: Image.Image) -> str:
    """Encode a PIL image as a JPEG base64 string for database storage."""
    with io.BytesIO() as buffer:
        image.convert("RGB").save(buffer, format="JPEG", quality=80)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


def image_from_base64(encoded: str) -> Image.Image:
    """Decode a base64-encoded JPEG string into a PIL Image."""
    image_data = base64.b64decode(encoded)
    return Image.open(io.BytesIO(image_data))


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
