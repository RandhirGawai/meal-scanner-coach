"""
database.py
------------
All data storage logic for the Meal Scanner + Body Recomposition Coach app.

Two backends, chosen automatically:

  LOCAL (default)  -> a SQLite file at data/app.db on this machine.
                       Great for running locally on your Mac.

  TURSO (optional)  -> a free, persistent cloud SQLite-compatible database
                        (https://turso.tech). Set TURSO_DATABASE_URL and
                        TURSO_AUTH_TOKEN (via .env locally, or Streamlit
                        Cloud Secrets when deployed) to switch to this.
                        Recommended once you host the app, since it makes
                        your data independent of the hosting platform's
                        disk — a Streamlit Cloud redeploy can't touch it.

Meal photos are stored as base64-encoded JPEG strings directly in the
`meals` table (not as separate files on disk). This means a SINGLE backup
of the database captures 100% of your data, photos included, and — when
using Turso — photos are just as persistent as the numbers.

Tables:
    profile        -> single-row table with user's stats & goals
    meals          -> one row per logged meal (with macro estimates + photo)
    body_metrics   -> one row per day of body composition logging
    activity       -> one row per day of workout/walk logging
"""

import json
from pathlib import Path
from datetime import date, datetime
from contextlib import contextmanager

from config import get_config

DB_PATH = Path(__file__).parent / "data" / "app.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

TURSO_DATABASE_URL = get_config("TURSO_DATABASE_URL", "").strip()
TURSO_AUTH_TOKEN = get_config("TURSO_AUTH_TOKEN", "").strip()
USE_TURSO = bool(TURSO_DATABASE_URL and TURSO_AUTH_TOKEN)

ALL_TABLES = ["profile", "meals", "body_metrics", "activity"]


# ---------------------------------------------------------------------------
# Connection handling — works the same way for both backends. Both libsql
# (Turso) and sqlite3 (local) support the same execute()/fetchall()/commit()
# style, so the rest of this file doesn't need to know which one is active.
# ---------------------------------------------------------------------------

@contextmanager
def get_conn():
    """Context manager so every caller gets a fresh connection that always closes."""
    if USE_TURSO:
        import libsql
        conn = libsql.connect(database=TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)
    else:
        import sqlite3
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)  # in case data/ was wiped
        conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _rows_to_dicts(cursor) -> list:
    """Convert a cursor's fetched rows into a list of plain dicts, using
    cursor.description for column names. Works for both sqlite3 and libsql
    without depending on backend-specific row-factory features."""
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _row_to_dict(cursor, row) -> dict:
    if row is None:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


def init_db():
    """Create tables if they don't exist yet. Safe to call every app start."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                name TEXT,
                sex TEXT,
                age INTEGER,
                height_cm REAL,
                goal TEXT,               -- 'fat_loss', 'muscle_gain', 'recomposition'
                activity_level TEXT,     -- 'sedentary','light','moderate','active','very_active'
                target_weight_kg REAL,
                protein_per_kg REAL DEFAULT 2.0,
                updated_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date TEXT NOT NULL,
                log_time TEXT NOT NULL,
                meal_type TEXT,           -- Breakfast/Lunch/Dinner/Snack
                image_base64 TEXT,        -- compressed JPEG, base64-encoded (stored in-DB for persistence)
                foods_json TEXT,          -- structured list of detected foods
                calories REAL,
                protein_g REAL,
                carbs_g REAL,
                fat_g REAL,
                fiber_g REAL,
                confidence TEXT,          -- High/Medium/Low/Manual entry
                ai_notes TEXT,
                user_notes TEXT,
                created_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS body_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date TEXT NOT NULL UNIQUE,
                weight_kg REAL,
                body_fat_pct REAL,
                muscle_kg REAL,
                water_pct REAL,
                bone_mass_kg REAL,
                visceral_fat REAL,
                notes TEXT,
                created_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date TEXT NOT NULL,
                workout_desc TEXT,
                workout_minutes REAL,
                walk_minutes REAL,
                steps INTEGER,
                notes TEXT,
                created_at TEXT
            )
        """)


# ---------------------------------------------------------------------------
# PROFILE
# ---------------------------------------------------------------------------

def save_profile(name, sex, age, height_cm, goal, activity_level, target_weight_kg, protein_per_kg):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO profile (id, name, sex, age, height_cm, goal, activity_level,
                                  target_weight_kg, protein_per_kg, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, sex=excluded.sex, age=excluded.age,
                height_cm=excluded.height_cm, goal=excluded.goal,
                activity_level=excluded.activity_level,
                target_weight_kg=excluded.target_weight_kg,
                protein_per_kg=excluded.protein_per_kg,
                updated_at=excluded.updated_at
        """, (name, sex, age, height_cm, goal, activity_level, target_weight_kg,
              protein_per_kg, datetime.now().isoformat()))


def get_profile():
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM profile WHERE id = 1")
        return _row_to_dict(cur, cur.fetchone())


# ---------------------------------------------------------------------------
# MEALS
# ---------------------------------------------------------------------------

def add_meal(log_date, log_time, meal_type, image_base64, foods, calories, protein_g,
             carbs_g, fat_g, fiber_g, confidence, ai_notes, user_notes=""):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO meals (log_date, log_time, meal_type, image_base64, foods_json,
                                calories, protein_g, carbs_g, fat_g, fiber_g,
                                confidence, ai_notes, user_notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (log_date, log_time, meal_type, image_base64, json.dumps(foods),
              calories, protein_g, carbs_g, fat_g, fiber_g, confidence,
              ai_notes, user_notes, datetime.now().isoformat()))


def get_meals_for_date(log_date):
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM meals WHERE log_date = ? ORDER BY log_time", (log_date,)
        )
        return _rows_to_dicts(cur)


def get_all_meals(limit=500):
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM meals ORDER BY log_date DESC, log_time DESC LIMIT ?", (limit,)
        )
        return _rows_to_dicts(cur)


def delete_meal(meal_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM meals WHERE id = ?", (meal_id,))


# ---------------------------------------------------------------------------
# BODY METRICS
# ---------------------------------------------------------------------------

def upsert_body_metrics(log_date, weight_kg, body_fat_pct, muscle_kg, water_pct,
                         bone_mass_kg=None, visceral_fat=None, notes=""):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO body_metrics (log_date, weight_kg, body_fat_pct, muscle_kg,
                                       water_pct, bone_mass_kg, visceral_fat, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(log_date) DO UPDATE SET
                weight_kg=excluded.weight_kg, body_fat_pct=excluded.body_fat_pct,
                muscle_kg=excluded.muscle_kg, water_pct=excluded.water_pct,
                bone_mass_kg=excluded.bone_mass_kg, visceral_fat=excluded.visceral_fat,
                notes=excluded.notes
        """, (log_date, weight_kg, body_fat_pct, muscle_kg, water_pct,
              bone_mass_kg, visceral_fat, notes, datetime.now().isoformat()))


def get_body_metrics_for_date(log_date):
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM body_metrics WHERE log_date = ?", (log_date,))
        return _row_to_dict(cur, cur.fetchone())


def get_all_body_metrics(limit=365):
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM body_metrics ORDER BY log_date DESC LIMIT ?", (limit,))
        return _rows_to_dicts(cur)


def get_latest_body_metrics():
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM body_metrics ORDER BY log_date DESC LIMIT 1")
        return _row_to_dict(cur, cur.fetchone())


# ---------------------------------------------------------------------------
# ACTIVITY
# ---------------------------------------------------------------------------

def upsert_activity(log_date, workout_desc, workout_minutes, walk_minutes, steps, notes=""):
    with get_conn() as conn:
        cur = conn.execute("SELECT id FROM activity WHERE log_date = ?", (log_date,))
        existing = cur.fetchone()
        if existing:
            conn.execute("""
                UPDATE activity SET workout_desc=?, workout_minutes=?, walk_minutes=?,
                                     steps=?, notes=? WHERE log_date=?
            """, (workout_desc, workout_minutes, walk_minutes, steps, notes, log_date))
        else:
            conn.execute("""
                INSERT INTO activity (log_date, workout_desc, workout_minutes, walk_minutes,
                                       steps, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (log_date, workout_desc, workout_minutes, walk_minutes, steps, notes,
                  datetime.now().isoformat()))


def get_activity_for_date(log_date):
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM activity WHERE log_date = ?", (log_date,))
        return _row_to_dict(cur, cur.fetchone())


def get_all_activity(limit=365):
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM activity ORDER BY log_date DESC LIMIT ?", (limit,))
        return _rows_to_dicts(cur)


# ---------------------------------------------------------------------------
# DAILY SUMMARY (used by AI Insights engine + History page)
# ---------------------------------------------------------------------------

def get_daily_totals(log_date):
    """Sum up all macros logged for a given day."""
    meals = get_meals_for_date(log_date)
    totals = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0}
    for m in meals:
        for k in totals:
            totals[k] += m.get(k) or 0
    totals["meal_count"] = len(meals)
    return totals


def get_last_n_days_summary(n=7):
    """Combined body/activity/nutrition summary for the last n days, oldest first."""
    from datetime import timedelta
    today = date.today()
    days = [(today - timedelta(days=i)).isoformat() for i in range(n)][::-1]

    summary = []
    for d in days:
        body = get_body_metrics_for_date(d)
        act = get_activity_for_date(d)
        totals = get_daily_totals(d)
        summary.append({
            "date": d,
            "weight_kg": body["weight_kg"] if body else None,
            "body_fat_pct": body["body_fat_pct"] if body else None,
            "muscle_kg": body["muscle_kg"] if body else None,
            "calories": totals["calories"],
            "protein_g": totals["protein_g"],
            "carbs_g": totals["carbs_g"],
            "fat_g": totals["fat_g"],
            "workout": act["workout_desc"] if act else None,
            "walk_minutes": act["walk_minutes"] if act else None,
            "steps": act["steps"] if act else None,
        })
    return summary


# ---------------------------------------------------------------------------
# BACKUP / RESTORE — full data export/import, backend-agnostic.
# Used by the sidebar's Backup & Restore panel. Because meal photos are
# stored as base64 text in the `meals` table (not separate files), this
# JSON export captures 100% of your data — numbers and photos — in one file.
# ---------------------------------------------------------------------------

def export_all_data() -> dict:
    with get_conn() as conn:
        data = {}
        for table in ALL_TABLES:
            cur = conn.execute(f"SELECT * FROM {table}")
            data[table] = _rows_to_dicts(cur)
    return data


def import_all_data(data: dict):
    """
    Restore a full backup, overwriting any existing rows with the same
    primary key. Unknown tables/columns in the backup are ignored so old
    backups still restore cleanly even if the schema evolves later.
    """
    with get_conn() as conn:
        for table in ALL_TABLES:
            rows = data.get(table, [])
            for row in rows:
                cols = list(row.keys())
                placeholders = ", ".join(["?"] * len(cols))
                col_list = ", ".join(cols)
                conn.execute(
                    f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})",
                    tuple(row.values()),
                )
