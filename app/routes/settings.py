from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db import connect
from app.scoring import STEPS_BUCKETS, WATER_BUCKETS

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=ROOT / "app" / "templates")
router = APIRouter()


def _upsert(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _parse_int_clamp(s, lo, hi, default):
    if s in (None, ""):
        return default
    try:
        return max(lo, min(hi, int(s)))
    except (TypeError, ValueError):
        return default


def _parse_float_clamp(s, lo, hi):
    """Return '' if input is empty/invalid, else clamped float as string."""
    if s in (None, ""):
        return ""
    try:
        v = max(lo, min(hi, float(s)))
        return str(v)
    except (TypeError, ValueError):
        return ""


@router.get("/settings", response_class=HTMLResponse)
def settings_get(request: Request) -> HTMLResponse:
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    s = {r["key"]: r["value"] for r in rows}
    return templates.TemplateResponse(request, "settings.html", {
        "forgiveness_enabled": s.get("streak_forgiveness_enabled", "1") == "1",
        "forgiveness_threshold": int(s.get("streak_forgiveness_threshold", "1") or "1"),
        "sleep_min_hours": s.get("sleep_min_hours", ""),
        "sleep_max_hours": s.get("sleep_max_hours", ""),
        "steps_min_bucket": s.get("steps_min_bucket", ""),
        "water_min_bucket": s.get("water_min_bucket", ""),
        "meals_min_count": s.get("meals_min_count", ""),
        "steps_buckets": STEPS_BUCKETS,
        "water_buckets": WATER_BUCKETS,
        "saved": request.query_params.get("saved") == "1",
    })


@router.post("/settings")
async def settings_post(request: Request):
    form = await request.form()
    forgiveness_enabled = "1" if form.get("streak_forgiveness_enabled") else "0"
    forgiveness_threshold = _parse_int_clamp(form.get("streak_forgiveness_threshold"), 0, 7, 1)

    sleep_min = _parse_float_clamp(form.get("sleep_min_hours"), 0, 14)
    sleep_max = _parse_float_clamp(form.get("sleep_max_hours"), 0, 14)

    raw_steps = form.get("steps_min_bucket")
    if raw_steps in (None, ""):
        steps_min = ""
    else:
        steps_min = str(_parse_int_clamp(raw_steps, 0, len(STEPS_BUCKETS) - 1, 0))

    raw_water = form.get("water_min_bucket")
    if raw_water in (None, ""):
        water_min = ""
    else:
        water_min = str(_parse_int_clamp(raw_water, 0, len(WATER_BUCKETS) - 1, 0))

    raw_meals = form.get("meals_min_count")
    if raw_meals in (None, ""):
        meals_min = ""
    else:
        meals_min = str(_parse_int_clamp(raw_meals, 0, 20, 0))

    with connect() as conn:
        _upsert(conn, "streak_forgiveness_enabled", forgiveness_enabled)
        _upsert(conn, "streak_forgiveness_threshold", str(forgiveness_threshold))
        _upsert(conn, "sleep_min_hours", sleep_min)
        _upsert(conn, "sleep_max_hours", sleep_max)
        _upsert(conn, "steps_min_bucket", steps_min)
        _upsert(conn, "water_min_bucket", water_min)
        _upsert(conn, "meals_min_count", meals_min)
    return RedirectResponse("/settings?saved=1", status_code=303)
