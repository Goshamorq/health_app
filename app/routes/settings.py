from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db import connect

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=ROOT / "app" / "templates")
router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
def settings_get(request: Request) -> HTMLResponse:
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    settings = {r["key"]: r["value"] for r in rows}
    return templates.TemplateResponse(request, "settings.html", {
        "forgiveness_enabled": settings.get("streak_forgiveness_enabled", "1") == "1",
        "forgiveness_threshold": int(settings.get("streak_forgiveness_threshold", "1") or "1"),
        "saved": request.query_params.get("saved") == "1",
    })


@router.post("/settings")
async def settings_post(request: Request):
    form = await request.form()
    enabled = "1" if form.get("streak_forgiveness_enabled") else "0"
    raw_threshold = form.get("streak_forgiveness_threshold") or "1"
    try:
        threshold = max(0, min(7, int(raw_threshold)))
    except ValueError:
        threshold = 1
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("streak_forgiveness_enabled", enabled),
        )
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("streak_forgiveness_threshold", str(threshold)),
        )
    return RedirectResponse("/settings?saved=1", status_code=303)
