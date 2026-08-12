"""
ai_engine.py
------------
All AI calls live here: meal-photo analysis (vision) and body-recomposition
coaching (text reasoning).

Primary path:  Groq API (free tier, no credit card) — fast + good quality.
Fallback path: local Ollama model (fully offline, zero cost, needs a Mac
                with enough RAM for a small vision-capable model).

Groq's model lineup changes periodically. As of Aug 2026 the recommended
free-tier models are set below as constants — if Groq deprecates one, just
update the constant, nothing else in the app needs to change.
"""

import os
import json
import base64
import re
from io import BytesIO

from dotenv import load_dotenv
from PIL import Image

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
USE_OLLAMA_FALLBACK = os.getenv("USE_OLLAMA_FALLBACK", "false").lower() == "true"
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llava")
OLLAMA_TEXT_MODEL = os.getenv("OLLAMA_TEXT_MODEL", "llama3.1")

# Groq model names — update here if Groq deprecates/renames a model.
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")
GROQ_TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "openai/gpt-oss-120b")

MAX_IMAGE_DIMENSION = 1024  # keep uploads small & fast for the free tier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_groq_client():
    from groq import Groq
    if not GROQ_API_KEY:
        raise RuntimeError(
            "No GROQ_API_KEY found. Add it to your .env file, or set "
            "USE_OLLAMA_FALLBACK=true to run fully offline with Ollama."
        )
    return Groq(api_key=GROQ_API_KEY)


def encode_image_to_base64(image: Image.Image) -> str:
    """Downscale + compress an image and return a base64 data URI (JPEG)."""
    image = image.convert("RGB")
    image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def _extract_json(text: str) -> dict:
    """
    LLMs sometimes wrap JSON in markdown fences, add a sentence before/after,
    or (for "thinking" models) prepend a <think>...</think> reasoning block.
    This strips all of that and pulls out the JSON object, raising a clear
    error if nothing usable is found.
    """
    text = text.strip()

    # Strip a complete <think>...</think> block if present.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # If there's an unclosed <think> tag, the response got cut off mid-reasoning
    # (usually means max_tokens was too low or reasoning wasn't disabled).
    if "<think>" in text and "</think>" not in text:
        raise ValueError(
            "The model's response was cut off while it was still 'thinking' and "
            "never reached the JSON answer. This usually means max_tokens was too "
            "low for this model, or its reasoning mode wasn't disabled. Try again — "
            "if it keeps happening, increase max_tokens in ai_engine.py."
        )

    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model response:\n{text[:500]}")
    return json.loads(match.group(0))


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

MEAL_VISION_SYSTEM_PROMPT = """You are an expert nutritionist and food-recognition AI with deep knowledge of Indian, \
Western, and global cuisine. You look at a photo of a meal and produce a precise, \
structured nutritional breakdown.

Rules:
1. Identify every distinct food/drink item visible in the photo.
2. Estimate a realistic portion size for each item using visual cues (plate size, \
utensils, hand for scale if visible, typical serving sizes).
3. For each item, estimate calories, protein (g), carbs (g), fat (g), and fiber (g) \
based on standard nutrition data (USDA / IFCT for Indian foods).
4. Sum the totals across all items.
5. Assign an overall confidence level: "High" (clear photo, familiar foods, easy to \
judge portions), "Medium" (some ambiguity in portion size or mixed/hidden ingredients), \
or "Low" (poor photo quality, unclear foods, heavily mixed dish where oil/ghee content \
is hard to judge).
6. If the image does not contain food, set "is_food" to false and explain why in "notes".

Respond with ONLY a single valid JSON object — no markdown fences, no commentary before \
or after — in exactly this shape:

{
  "is_food": true,
  "foods": [
    {"name": "Grilled chicken breast", "estimated_quantity": "150g", "calories": 240, "protein_g": 45, "carbs_g": 0, "fat_g": 5, "fiber_g": 0}
  ],
  "totals": {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0},
  "confidence": "High",
  "notes": "One short sentence flagging any major assumptions (e.g. 'assumed 1 tbsp oil used in cooking')."
}"""

MEAL_TEXT_CORRECTION_SYSTEM_PROMPT = """You are an expert nutritionist with deep knowledge of Indian, Western, and global \
cuisine. A user previously had a meal photo analyzed by AI, but the result was wrong or \
incomplete, so they are now telling you IN THEIR OWN WORDS what the meal actually \
contained. Trust the user's description completely — it is more reliable than any visual \
guess. Your job is only to convert their description into a precise structured nutrition \
breakdown.

Rules:
1. Parse every distinct food/drink item the user mentions, including quantities if given.
2. If the user gives a quantity (e.g. "2 rotis", "1 cup rice", "200g paneer"), use it exactly.
3. If no quantity is given for an item, assume a typical single serving size and say so in "notes".
4. Estimate calories, protein (g), carbs (g), fat (g), and fiber (g) per item using standard \
nutrition data (USDA / IFCT for Indian foods).
5. Sum the totals across all items.
6. Confidence should be "High" whenever the user gave clear items and quantities — you are \
no longer guessing from a photo, so confidence should rarely be "Low" here.

Respond with ONLY a single valid JSON object — no markdown fences, no commentary before \
or after — in exactly this same shape used for photo analysis:

{
  "is_food": true,
  "foods": [
    {"name": "Grilled chicken breast", "estimated_quantity": "150g", "calories": 240, "protein_g": 45, "carbs_g": 0, "fat_g": 5, "fiber_g": 0}
  ],
  "totals": {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0},
  "confidence": "High",
  "notes": "One short sentence noting any assumed quantities."
}"""

COACH_SYSTEM_PROMPT = """You are an elite body-recomposition coach and sports nutritionist. Your client's goal \
is to LOSE BODY FAT while BUILDING/PRESERVING MUSCLE (body recomposition) — the hardest \
and most nuanced physique goal, requiring a modest calorie approach, high protein, and \
resistance training. You give direct, specific, encouraging advice — never vague platitudes.

You will be given the client's profile, today's logged meals, today's body metrics (if \
logged), today's activity, and their recent daily history. Use it all.

Core principles you always apply:
- Body recomposition works best with a small calorie deficit (~10-20% below maintenance) \
or at maintenance, combined with high protein (1.6-2.4 g/kg bodyweight) and resistance training.
- Protein is the single most important lever for recomposition — always calculate and state \
a clear daily protein target and gap.
- Fiber (25-35g/day) and adequate water support fat loss and satiety.
- Consistency over days/weeks matters far more than any single meal.
- Be specific: name numbers, not generalities ("you need 38g more protein today", not \
"eat more protein").

Respond with ONLY a single valid JSON object — no markdown fences, no commentary — in \
exactly this shape:

{
  "meal_verdict": "1-2 sentences judging how good the most recent meal is for the client's fat-loss/muscle-building goal.",
  "daily_calorie_target": 0,
  "daily_protein_target_g": 0,
  "protein_so_far_g": 0,
  "protein_remaining_g": 0,
  "calories_so_far": 0,
  "calories_remaining": 0,
  "fat_loss_muscle_gain_tip": "One specific, actionable tip for today.",
  "weekly_trend_analysis": "2-3 sentences on the trend across the recent days provided, or 'Not enough data yet — log at least 3-4 days for a trend.' if insufficient.",
  "overall_summary": "A short, encouraging 2-3 sentence wrap-up in a motivating coach tone."
}"""


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def analyze_meal_image(image: Image.Image) -> dict:
    """
    Send a meal photo to the vision model and get back structured macro data.
    Returns a dict matching MEAL_VISION_SYSTEM_PROMPT's JSON shape.
    Raises RuntimeError with a friendly message on failure.
    """
    data_uri = encode_image_to_base64(image)

    if USE_OLLAMA_FALLBACK:
        return _analyze_meal_ollama(data_uri)

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=GROQ_VISION_MODEL,
            messages=[
                {"role": "system", "content": MEAL_VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this meal photo and return the JSON breakdown."},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                },
            ],
            temperature=0.3,
            max_tokens=2000,
            # qwen3.6-27b defaults to a "thinking" mode that writes a long
            # <think>...</think> block before answering, which can eat the
            # whole token budget before it ever reaches the JSON. We don't
            # need deep reasoning to identify food in a photo, so disable it.
            reasoning_effort="none",
        )
        raw = response.choices[0].message.content
        return _extract_json(raw)

    except Exception as e:
        raise RuntimeError(
            f"Groq vision analysis failed ({e}). Check your GROQ_API_KEY, your "
            f"internet connection, or try again in a moment (free tier rate limits)."
        )


def analyze_meal_text(description: str) -> dict:
    """
    Used when the user says the AI's photo analysis was wrong and types out
    what the meal actually was (e.g. "2 rotis, 1 bowl palak paneer, small
    side of rice"). Returns the same JSON shape as analyze_meal_image, so
    the UI can reuse the same review/edit/save flow.
    """
    if USE_OLLAMA_FALLBACK:
        return _analyze_meal_text_ollama(description)

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=GROQ_TEXT_MODEL,
            messages=[
                {"role": "system", "content": MEAL_TEXT_CORRECTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"The meal is: {description}"},
            ],
            temperature=0.3,
            max_tokens=1500,
            reasoning_effort="low",
            reasoning_format="parsed",
        )
        raw = response.choices[0].message.content
        return _extract_json(raw)

    except Exception as e:
        raise RuntimeError(
            f"Groq text analysis failed ({e}). Check your GROQ_API_KEY, your "
            f"internet connection, or try again in a moment (free tier rate limits)."
        )


def _analyze_meal_text_ollama(description: str) -> dict:
    import requests
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_TEXT_MODEL,
                "prompt": MEAL_TEXT_CORRECTION_SYSTEM_PROMPT
                + f"\n\nThe meal is: {description}\n\nReturn ONLY the JSON breakdown.",
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        return _extract_json(raw)
    except Exception as e:
        raise RuntimeError(
            f"Ollama text analysis failed ({e}). Make sure Ollama is running "
            f"(`ollama serve`) and you've pulled a text model (`ollama pull {OLLAMA_TEXT_MODEL}`)."
        )


def _analyze_meal_ollama(data_uri: str) -> dict:
    """Fallback: fully offline meal analysis via a local Ollama vision model."""
    import requests
    b64_only = data_uri.split(",", 1)[1]
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_VISION_MODEL,
                "prompt": MEAL_VISION_SYSTEM_PROMPT
                + "\n\nAnalyze this meal photo and return ONLY the JSON breakdown.",
                "images": [b64_only],
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        return _extract_json(raw)
    except Exception as e:
        raise RuntimeError(
            f"Ollama vision analysis failed ({e}). Make sure Ollama is running "
            f"(`ollama serve`) and you've pulled a vision model (`ollama pull {OLLAMA_VISION_MODEL}`)."
        )


def generate_insights(profile: dict, today_meals: list, today_body: dict,
                       today_activity: dict, recent_history: list) -> dict:
    """
    Build the coaching prompt from all logged data and return structured
    insights matching COACH_SYSTEM_PROMPT's JSON shape.
    """
    context = {
        "client_profile": profile or "Not set — use general recomposition guidelines "
                                      "(assume moderately active adult).",
        "today_meals_logged": today_meals,
        "today_body_metrics": today_body or "Not logged today.",
        "today_activity": today_activity or "Not logged today.",
        "recent_daily_history": recent_history,
    }

    user_message = (
        "Here is the client's full data. Analyze it and return the JSON insight object "
        "as specified in your instructions.\n\n" + json.dumps(context, indent=2, default=str)
    )

    if USE_OLLAMA_FALLBACK:
        return _generate_insights_ollama(user_message)

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=GROQ_TEXT_MODEL,
            messages=[
                {"role": "system", "content": COACH_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.4,
            max_tokens=2000,
            # gpt-oss models always reason internally; reasoning_format="parsed"
            # keeps that reasoning out of message.content so we get clean JSON.
            reasoning_effort="low",
            reasoning_format="parsed",
        )
        raw = response.choices[0].message.content
        return _extract_json(raw)

    except Exception as e:
        raise RuntimeError(
            f"Groq insights generation failed ({e}). Check your GROQ_API_KEY, your "
            f"internet connection, or try again shortly (free tier rate limits)."
        )


def _generate_insights_ollama(user_message: str) -> dict:
    import requests
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_TEXT_MODEL,
                "prompt": COACH_SYSTEM_PROMPT + "\n\n" + user_message,
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        return _extract_json(raw)
    except Exception as e:
        raise RuntimeError(
            f"Ollama insights generation failed ({e}). Make sure Ollama is running "
            f"(`ollama serve`) and you've pulled a text model (`ollama pull {OLLAMA_TEXT_MODEL}`)."
        )


# ---------------------------------------------------------------------------
# Calorie / protein target calculator (deterministic, no AI needed)
# Used as a sane fallback/cross-check even when the AI insight call succeeds.
# ---------------------------------------------------------------------------

ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}


def calculate_targets(profile: dict, latest_body: dict) -> dict:
    """
    Mifflin-St Jeor BMR -> TDEE -> recomposition targets.
    Returns dict with calorie_target, protein_target_g, maintenance_calories.
    Falls back to reasonable defaults if data is missing.
    """
    if not profile or not latest_body or not latest_body.get("weight_kg"):
        return {
            "maintenance_calories": None,
            "calorie_target": None,
            "protein_target_g": None,
            "note": "Log your profile (Settings) and today's weight to get precise targets.",
        }

    weight = latest_body["weight_kg"]
    height = profile.get("height_cm") or 170
    age = profile.get("age") or 30
    sex = (profile.get("sex") or "male").lower()

    if sex == "male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    multiplier = ACTIVITY_MULTIPLIERS.get(profile.get("activity_level"), 1.55)
    tdee = bmr * multiplier

    goal = profile.get("goal", "recomposition")
    if goal == "fat_loss":
        calorie_target = tdee * 0.80
    elif goal == "muscle_gain":
        calorie_target = tdee * 1.08
    else:  # recomposition
        calorie_target = tdee * 0.90

    protein_per_kg = profile.get("protein_per_kg") or 2.0
    protein_target = weight * protein_per_kg

    return {
        "maintenance_calories": round(tdee),
        "calorie_target": round(calorie_target),
        "protein_target_g": round(protein_target),
        "note": None,
    }
