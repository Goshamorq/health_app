import json
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.db import connect
from app.scoring import ALL_PILLARS, STEPS_BUCKETS, WATER_BUCKETS

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=ROOT / "app" / "templates")

router = APIRouter()

PILLARS = ALL_PILLARS
HABIT_TYPES = ("binary", "time", "quantity")


def _build_threshold(habit_type: str, target: str | None, direction: str | None,
                     bucket_labels: str | None, min_done_bucket: int | None) -> str:
    if habit_type == "binary":
        return "{}"
    if habit_type == "time":
        if not target or direction not in ("before", "after"):
            raise HTTPException(400, "time habit requires target and direction")
        return json.dumps({"target": target, "direction": direction})
    if habit_type == "quantity":
        labels = [s.strip() for s in (bucket_labels or "").split(",") if s.strip()]
        if not labels:
            raise HTTPException(400, "quantity habit requires at least one bucket label")
        if min_done_bucket is None or not (0 <= min_done_bucket < len(labels)):
            raise HTTPException(400, "min_done_bucket out of range")
        return json.dumps({"bucket_labels": labels, "min_done_bucket": min_done_bucket})
    raise HTTPException(400, f"unknown habit type: {habit_type}")


def _load_habits() -> dict:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, pillar, name, type, threshold_config, archived "
            "FROM habits ORDER BY archived, pillar, id"
        ).fetchall()
    active_by_pillar = {p: [] for p in PILLARS}
    archived: list = []
    for r in rows:
        item = {
            "id": r["id"],
            "pillar": r["pillar"],
            "name": r["name"],
            "type": r["type"],
            "threshold": json.loads(r["threshold_config"]),
        }
        if r["archived"]:
            archived.append(item)
        else:
            active_by_pillar[r["pillar"]].append(item)
    return {"active_by_pillar": active_by_pillar, "archived": archived, "pillars": PILLARS}


def _render_list(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "_habits_list.html", _load_habits())


@router.get("/habits", response_class=HTMLResponse)
def list_habits(request: Request) -> HTMLResponse:
    ctx = _load_habits()
    with connect() as conn:
        settings_rows = conn.execute("SELECT key, value FROM settings").fetchall()
    s = {r["key"]: r["value"] for r in settings_rows}
    ctx["sleep_min_hours"] = s.get("sleep_min_hours", "")
    ctx["sleep_max_hours"] = s.get("sleep_max_hours", "")
    ctx["sleep_bedtime_std_max_min"] = s.get("sleep_bedtime_std_max_min", "")
    ctx["sleep_min_bedtime_samples"] = s.get("sleep_min_bedtime_samples", "")
    ctx["steps_min_bucket"] = s.get("steps_min_bucket", "")
    ctx["water_min_bucket"] = s.get("water_min_bucket", "")
    ctx["meals_min_count"] = s.get("meals_min_count", "")
    ctx["steps_buckets"] = STEPS_BUCKETS
    ctx["water_buckets"] = WATER_BUCKETS
    ctx["thresholds_saved"] = request.query_params.get("thresholds_saved") == "1"
    return templates.TemplateResponse(request, "habits.html", ctx)


@router.post("/habits", response_class=HTMLResponse)
def create_habit(
    request: Request,
    pillar: str = Form(...),
    name: str = Form(...),
    type: str = Form(...),
    target: str | None = Form(None),
    direction: str | None = Form(None),
    bucket_labels: str | None = Form(None),
    min_done_bucket: int | None = Form(None),
) -> HTMLResponse:
    if pillar not in PILLARS:
        raise HTTPException(400, f"invalid pillar: {pillar}")
    if type not in HABIT_TYPES:
        raise HTTPException(400, f"invalid type: {type}")
    name = name.strip()
    if not name:
        raise HTTPException(400, "name is required")
    threshold = _build_threshold(type, target, direction, bucket_labels, min_done_bucket)
    with connect() as conn:
        conn.execute(
            "INSERT INTO habits (pillar, name, type, threshold_config) VALUES (?, ?, ?, ?)",
            (pillar, name, type, threshold),
        )
    return _render_list(request)


@router.post("/habits/{habit_id}/rename", response_class=HTMLResponse)
def rename_habit(request: Request, habit_id: int, name: str = Form(...)) -> HTMLResponse:
    name = name.strip()
    if not name:
        raise HTTPException(400, "name is required")
    with connect() as conn:
        cur = conn.execute("UPDATE habits SET name = ? WHERE id = ?", (name, habit_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "habit not found")
    return _render_list(request)


@router.post("/habits/{habit_id}/archive", response_class=HTMLResponse)
def archive_habit(request: Request, habit_id: int) -> HTMLResponse:
    with connect() as conn:
        cur = conn.execute("UPDATE habits SET archived = 1 WHERE id = ?", (habit_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "habit not found")
    return _render_list(request)


@router.post("/habits/{habit_id}/unarchive", response_class=HTMLResponse)
def unarchive_habit(request: Request, habit_id: int) -> HTMLResponse:
    with connect() as conn:
        cur = conn.execute("UPDATE habits SET archived = 0 WHERE id = ?", (habit_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "habit not found")
    return _render_list(request)
