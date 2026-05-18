from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.db import connect

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=ROOT / "app" / "templates")
router = APIRouter()

ALLOWED_TAGS = ("stress", "social", "boredom", "other")


def _load_entries(conn, limit: int = 30) -> list[dict]:
    rows = conn.execute(
        "SELECT id, datetime(ts, 'localtime') AS ts, text, tag "
        "FROM trigger_entries ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/trigger", response_class=HTMLResponse)
def trigger_get(request: Request) -> HTMLResponse:
    with connect() as conn:
        entries = _load_entries(conn)
    return templates.TemplateResponse(request, "trigger.html", {
        "entries": entries,
        "allowed_tags": ALLOWED_TAGS,
    })


@router.post("/trigger", response_class=HTMLResponse)
async def trigger_post(request: Request,
                        text: str = Form(...),
                        tag: str = Form(...)) -> HTMLResponse:
    text = text.strip()
    if not text:
        raise HTTPException(400, "text required")
    if tag not in ALLOWED_TAGS:
        raise HTTPException(400, f"invalid tag: {tag}")
    with connect() as conn:
        conn.execute(
            "INSERT INTO trigger_entries (text, tag) VALUES (?, ?)",
            (text, tag),
        )
        entries = _load_entries(conn)
    return templates.TemplateResponse(request, "_trigger_list.html", {"entries": entries})


@router.delete("/trigger/{entry_id}", response_class=HTMLResponse)
def trigger_delete(request: Request, entry_id: int) -> HTMLResponse:
    with connect() as conn:
        cur = conn.execute("DELETE FROM trigger_entries WHERE id = ?", (entry_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "entry not found")
        entries = _load_entries(conn)
    return templates.TemplateResponse(request, "_trigger_list.html", {"entries": entries})
