import json
from datetime import date as date_cls, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db import connect
from app.scoring import ALL_PILLARS, STEPS_BUCKETS, WATER_BUCKETS, WEEKDAY_SHORT, is_done, parse_habit_input

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=ROOT / "app" / "templates")
router = APIRouter()

PILLARS = ALL_PILLARS
RATING_VALUES = (1, 2, 3, 4, 5)


def _parse_date(s: str | None) -> str:
    if not s:
        return date_cls.today().isoformat()
    try:
        return date_cls.fromisoformat(s).isoformat()
    except ValueError:
        raise HTTPException(400, f"invalid date: {s}")


def _load_hub_context(target_date: str) -> dict:
    today_iso = date_cls.today().isoformat()
    with connect() as conn:
        habits = conn.execute(
            "SELECT id, pillar, name, type, threshold_config "
            "FROM habits WHERE archived = 0 ORDER BY pillar, id"
        ).fetchall()
        checkin = conn.execute(
            "SELECT * FROM checkins WHERE date = ?", (target_date,)
        ).fetchone()
        entries = conn.execute(
            "SELECT habit_id, value_json, done FROM habit_entries WHERE checkin_date = ?",
            (target_date,),
        ).fetchall()
    entries_by_habit = {
        e["habit_id"]: {"value": json.loads(e["value_json"]), "done": bool(e["done"])}
        for e in entries
    }
    habits_by_pillar: dict[str, list[dict]] = {p: [] for p in PILLARS}
    for h in habits:
        habits_by_pillar[h["pillar"]].append({
            "id": h["id"],
            "name": h["name"],
            "type": h["type"],
            "threshold": json.loads(h["threshold_config"]),
            "entry": entries_by_habit.get(h["id"]),
        })
    d = date_cls.fromisoformat(target_date)
    return {
        "target_date": target_date,
        "target_weekday": WEEKDAY_SHORT[d.weekday()],
        "is_today": target_date == today_iso,
        "today": today_iso,
        "prev_date": (d - timedelta(days=1)).isoformat(),
        "next_date": (d + timedelta(days=1)).isoformat(),
        "has_data": checkin is not None,
        "checkin": dict(checkin) if checkin else None,
        "habits_by_pillar": habits_by_pillar,
        "pillars": PILLARS,
        "water_buckets": WATER_BUCKETS,
        "steps_buckets": STEPS_BUCKETS,
        "rating_values": RATING_VALUES,
    }


@router.get("/checkin", response_class=HTMLResponse)
def checkin_get(request: Request, date: str | None = None) -> HTMLResponse:
    target_date = _parse_date(date)
    return templates.TemplateResponse(request, "checkin.html", _load_hub_context(target_date))


def _int_or_none(s: str | None) -> int | None:
    if s in (None, ""):
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _float_or_none(s: str | None) -> float | None:
    if s in (None, ""):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _text_or_none(s: str | None) -> str | None:
    if s in (None, ""):
        return None
    return s


def _bucket_or_none(s: str | None, allowed: tuple[str, ...]) -> str | None:
    if not s:
        return None
    return s if s in allowed else None


@router.post("/checkin")
async def save_checkin(request: Request):
    form = await request.form()
    target_date = _parse_date(form.get("date"))

    sleep_hours = _float_or_none(form.get("sleep_hours"))
    bedtime = _text_or_none(form.get("bedtime"))
    mood_am = _int_or_none(form.get("mood_am"))
    mood_pm = _int_or_none(form.get("mood_pm"))
    water = _bucket_or_none(form.get("water_bucket"), WATER_BUCKETS)
    steps = _bucket_or_none(form.get("steps_bucket"), STEPS_BUCKETS)
    food_text = _text_or_none(form.get("food_text"))
    note_text = _text_or_none(form.get("note_text"))
    meals_count = _int_or_none(form.get("meals_count"))

    with connect() as conn:
        conn.execute(
            """INSERT INTO checkins
                (date, sleep_hours, bedtime, mood_am, mood_pm,
                 water_bucket, steps_bucket,
                 food_text, note_text, meals_count, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(date) DO UPDATE SET
                 sleep_hours = excluded.sleep_hours,
                 bedtime = excluded.bedtime,
                 mood_am = excluded.mood_am,
                 mood_pm = excluded.mood_pm,
                 water_bucket = excluded.water_bucket,
                 steps_bucket = excluded.steps_bucket,
                 food_text = excluded.food_text,
                 note_text = excluded.note_text,
                 meals_count = excluded.meals_count,
                 updated_at = datetime('now')""",
            (target_date, sleep_hours, bedtime, mood_am, mood_pm,
             water, steps,
             food_text, note_text, meals_count),
        )

        habits = conn.execute(
            "SELECT id, type, threshold_config FROM habits WHERE archived = 0"
        ).fetchall()
        for h in habits:
            raw = form.get(f"habit_{h['id']}")
            threshold = json.loads(h["threshold_config"])
            value = parse_habit_input(h["type"], raw)
            done = is_done(h["type"], threshold, value)
            conn.execute(
                """INSERT INTO habit_entries (checkin_date, habit_id, value_json, done)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(checkin_date, habit_id) DO UPDATE SET
                     value_json = excluded.value_json,
                     done = excluded.done""",
                (target_date, h["id"], json.dumps(value), int(done)),
            )

    return RedirectResponse(f"/checkin?date={target_date}", status_code=303)


@router.post("/checkin/reset")
async def reset_checkin(request: Request):
    form = await request.form()
    target_date = _parse_date(form.get("date"))
    with connect() as conn:
        # ON DELETE CASCADE on habit_entries(checkin_date) wipes that day's entries.
        conn.execute("DELETE FROM checkins WHERE date = ?", (target_date,))
    return RedirectResponse(f"/checkin?date={target_date}", status_code=303)


@router.post("/checkin/copy-previous")
async def copy_previous(request: Request):
    form = await request.form()
    target_date = _parse_date(form.get("date"))
    with connect() as conn:
        prev = conn.execute(
            "SELECT * FROM checkins WHERE date < ? ORDER BY date DESC LIMIT 1",
            (target_date,),
        ).fetchone()
        if prev is None:
            return RedirectResponse(f"/checkin?date={target_date}", status_code=303)
        prev_date = prev["date"]
        conn.execute(
            """INSERT INTO checkins
                (date, sleep_hours, bedtime, mood_am, mood_pm,
                 water_bucket, steps_bucket,
                 food_text, note_text, meals_count, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(date) DO UPDATE SET
                 sleep_hours = excluded.sleep_hours,
                 bedtime = excluded.bedtime,
                 mood_am = excluded.mood_am,
                 mood_pm = excluded.mood_pm,
                 water_bucket = excluded.water_bucket,
                 steps_bucket = excluded.steps_bucket,
                 food_text = excluded.food_text,
                 note_text = excluded.note_text,
                 meals_count = excluded.meals_count,
                 updated_at = datetime('now')""",
            (target_date, prev["sleep_hours"], prev["bedtime"], prev["mood_am"],
             prev["mood_pm"], prev["water_bucket"], prev["steps_bucket"],
             prev["food_text"], prev["note_text"], prev["meals_count"]),
        )
        conn.execute(
            """INSERT INTO habit_entries (checkin_date, habit_id, value_json, done)
               SELECT ?, he.habit_id, he.value_json, he.done
               FROM habit_entries he
               JOIN habits h ON h.id = he.habit_id
               WHERE he.checkin_date = ? AND h.archived = 0
               ON CONFLICT(checkin_date, habit_id) DO UPDATE SET
                 value_json = excluded.value_json,
                 done = excluded.done""",
            (target_date, prev_date),
        )
    return RedirectResponse(f"/checkin?date={target_date}", status_code=303)
