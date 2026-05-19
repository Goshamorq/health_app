from datetime import date as date_cls
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db import connect

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=ROOT / "app" / "templates")
router = APIRouter()

GOAL_STATUSES = ("draft", "active", "completed", "failed", "archived")
TERMINAL_STATUSES = ("completed", "failed", "archived")
ALLOWED_TRIGGER_TAGS = ("stress", "social", "boredom", "other")


# ---------- /journal landing redirect ----------

@router.get("/journal", response_class=HTMLResponse)
def journal_root():
    return RedirectResponse("/journal/goals", status_code=303)


# ---------- Goals ----------

def _today() -> str:
    return date_cls.today().isoformat()


def _validate_date(s: str) -> str:
    try:
        return date_cls.fromisoformat(s).isoformat()
    except ValueError:
        raise HTTPException(400, f"invalid deadline date: {s}")


def _load_goals(conn) -> dict:
    rows = conn.execute(
        "SELECT * FROM goals ORDER BY "
        "CASE status WHEN 'active' THEN 0 WHEN 'draft' THEN 1 "
        "WHEN 'completed' THEN 2 WHEN 'failed' THEN 3 ELSE 4 END, "
        "deadline ASC, id DESC"
    ).fetchall()
    today = _today()
    out = {"active": None, "drafts": [], "completed": [], "failed": [], "archived": []}
    for r in rows:
        g = dict(r)
        if g["status"] == "active":
            g["is_overdue"] = g["deadline"] < today
            g["days_left"] = (date_cls.fromisoformat(g["deadline"])
                              - date_cls.fromisoformat(today)).days
            out["active"] = g
        elif g["status"] == "draft":
            out["drafts"].append(g)
        elif g["status"] == "completed":
            out["completed"].append(g)
        elif g["status"] == "failed":
            out["failed"].append(g)
        else:
            out["archived"].append(g)
    return out


def _goals_context(conn, request: Request) -> dict:
    return {
        "active_tab": "goals",
        "today": _today(),
        "goals": _load_goals(conn),
        "saved": request.query_params.get("saved") == "1",
    }


@router.get("/journal/goals", response_class=HTMLResponse)
def goals_get(request: Request) -> HTMLResponse:
    with connect() as conn:
        ctx = _goals_context(conn, request)
    return templates.TemplateResponse(request, "journal_goals.html", ctx)


def _form_text(form, key: str, max_len: int = 2000) -> str | None:
    v = form.get(key)
    if v is None:
        return None
    v = v.strip()
    return v[:max_len] if v else None


@router.post("/journal/goals")
async def goals_create(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    deadline = _validate_date((form.get("deadline") or "").strip())
    reward = _form_text(form, "reward")
    punishment = _form_text(form, "punishment")
    with connect() as conn:
        conn.execute(
            "INSERT INTO goals (name, reward, punishment, deadline, status) "
            "VALUES (?, ?, ?, ?, 'draft')",
            (name[:120], reward, punishment, deadline),
        )
    return RedirectResponse("/journal/goals?saved=1", status_code=303)


def _require_goal(conn, goal_id: int):
    row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "goal not found")
    return row


@router.post("/journal/goals/{goal_id}/edit")
async def goals_edit(goal_id: int, request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    deadline = _validate_date((form.get("deadline") or "").strip())
    reward = _form_text(form, "reward")
    punishment = _form_text(form, "punishment")
    with connect() as conn:
        g = _require_goal(conn, goal_id)
        if g["status"] in TERMINAL_STATUSES:
            raise HTTPException(400, f"cannot edit a {g['status']} goal")
        conn.execute(
            "UPDATE goals SET name = ?, reward = ?, punishment = ?, deadline = ? "
            "WHERE id = ?",
            (name[:120], reward, punishment, deadline, goal_id),
        )
    return RedirectResponse("/journal/goals?saved=1", status_code=303)


@router.post("/journal/goals/{goal_id}/activate")
def goals_activate(goal_id: int):
    with connect() as conn:
        g = _require_goal(conn, goal_id)
        if g["status"] != "draft":
            raise HTTPException(400, f"can only activate drafts (this is {g['status']})")
        try:
            conn.execute(
                "UPDATE goals SET status = 'active', activated_at = datetime('now','localtime') "
                "WHERE id = ?",
                (goal_id,),
            )
        except Exception as exc:
            # partial unique index hit — another goal is already active
            raise HTTPException(409,
                "another goal is already active — close or deactivate it first") from exc
    return RedirectResponse("/journal/goals", status_code=303)


@router.post("/journal/goals/{goal_id}/deactivate")
def goals_deactivate(goal_id: int):
    with connect() as conn:
        g = _require_goal(conn, goal_id)
        if g["status"] != "active":
            raise HTTPException(400, f"goal is not active (status={g['status']})")
        conn.execute(
            "UPDATE goals SET status = 'draft', activated_at = NULL WHERE id = ?",
            (goal_id,),
        )
    return RedirectResponse("/journal/goals", status_code=303)


def _close_goal(goal_id: int, new_status: str, closing_note: str | None):
    if new_status not in ("completed", "failed"):
        raise HTTPException(400, "invalid close status")
    with connect() as conn:
        g = _require_goal(conn, goal_id)
        if g["status"] not in ("active", "completed", "failed"):
            raise HTTPException(400, f"cannot close from status={g['status']}")
        conn.execute(
            "UPDATE goals SET status = ?, closed_at = datetime('now','localtime'), "
            "closing_note = ? WHERE id = ?",
            (new_status, closing_note, goal_id),
        )


def _safe_back(form) -> str:
    """Allow the caller to specify a redirect target. Restricted to same-origin
    paths (must start with /, no // protocol-relative or full URLs)."""
    back = (form.get("back") or "").strip()
    if back.startswith("/") and not back.startswith("//"):
        return back
    return "/journal/goals?saved=1"


@router.post("/journal/goals/{goal_id}/complete")
async def goals_complete(goal_id: int, request: Request):
    form = await request.form()
    _close_goal(goal_id, "completed", _form_text(form, "closing_note"))
    return RedirectResponse(_safe_back(form), status_code=303)


@router.post("/journal/goals/{goal_id}/fail")
async def goals_fail(goal_id: int, request: Request):
    form = await request.form()
    _close_goal(goal_id, "failed", _form_text(form, "closing_note"))
    return RedirectResponse(_safe_back(form), status_code=303)


@router.post("/journal/goals/{goal_id}/archive")
def goals_archive(goal_id: int):
    with connect() as conn:
        g = _require_goal(conn, goal_id)
        if g["status"] == "active":
            raise HTTPException(400, "deactivate or close an active goal before archiving")
        conn.execute(
            "UPDATE goals SET status = 'archived', closed_at = "
            "COALESCE(closed_at, datetime('now','localtime')) WHERE id = ?",
            (goal_id,),
        )
    return RedirectResponse("/journal/goals", status_code=303)


@router.post("/journal/goals/{goal_id}/unarchive")
def goals_unarchive(goal_id: int):
    with connect() as conn:
        g = _require_goal(conn, goal_id)
        if g["status"] != "archived":
            raise HTTPException(400, "not archived")
        conn.execute(
            "UPDATE goals SET status = 'draft', closed_at = NULL, closing_note = NULL "
            "WHERE id = ?",
            (goal_id,),
        )
    return RedirectResponse("/journal/goals", status_code=303)


@router.delete("/journal/goals/{goal_id}")
def goals_delete(goal_id: int):
    with connect() as conn:
        g = _require_goal(conn, goal_id)
        if g["status"] != "draft":
            raise HTTPException(400, "only drafts can be hard-deleted; archive instead")
        conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    return RedirectResponse("/journal/goals", status_code=303)


# ---------- Triggers (moved under /journal/triggers) ----------

def _load_trigger_entries(conn, limit: int = 30) -> list[dict]:
    rows = conn.execute(
        "SELECT id, datetime(ts, 'localtime') AS ts, text, tag "
        "FROM trigger_entries ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/journal/triggers", response_class=HTMLResponse)
def triggers_get(request: Request) -> HTMLResponse:
    with connect() as conn:
        entries = _load_trigger_entries(conn)
    return templates.TemplateResponse(request, "journal_triggers.html", {
        "active_tab": "triggers",
        "entries": entries,
        "allowed_tags": ALLOWED_TRIGGER_TAGS,
    })


def _trigger_list_response(request: Request, entries: list[dict]) -> HTMLResponse:
    return templates.TemplateResponse(request, "_trigger_list.html", {
        "entries": entries,
        "allowed_tags": ALLOWED_TRIGGER_TAGS,
    })


@router.post("/journal/triggers", response_class=HTMLResponse)
async def triggers_create(request: Request,
                           text: str = Form(...),
                           tag: str = Form(...)) -> HTMLResponse:
    text = text.strip()
    if not text:
        raise HTTPException(400, "text required")
    if tag not in ALLOWED_TRIGGER_TAGS:
        raise HTTPException(400, f"invalid tag: {tag}")
    with connect() as conn:
        conn.execute("INSERT INTO trigger_entries (text, tag) VALUES (?, ?)", (text, tag))
        entries = _load_trigger_entries(conn)
    return _trigger_list_response(request, entries)


@router.post("/journal/triggers/{entry_id}/edit", response_class=HTMLResponse)
async def triggers_edit(request: Request, entry_id: int,
                         text: str = Form(...),
                         tag: str = Form(...)) -> HTMLResponse:
    text = text.strip()
    if not text:
        raise HTTPException(400, "text required")
    if tag not in ALLOWED_TRIGGER_TAGS:
        raise HTTPException(400, f"invalid tag: {tag}")
    with connect() as conn:
        cur = conn.execute(
            "UPDATE trigger_entries SET text = ?, tag = ? WHERE id = ?",
            (text, tag, entry_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "entry not found")
        entries = _load_trigger_entries(conn)
    return _trigger_list_response(request, entries)


@router.delete("/journal/triggers/{entry_id}", response_class=HTMLResponse)
def triggers_delete(request: Request, entry_id: int) -> HTMLResponse:
    with connect() as conn:
        cur = conn.execute("DELETE FROM trigger_entries WHERE id = ?", (entry_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "entry not found")
        entries = _load_trigger_entries(conn)
    return _trigger_list_response(request, entries)


# ---------- Daily notes (from /checkin's note_text) ----------

def _load_notes(conn, limit: int = 90) -> list[dict]:
    rows = conn.execute(
        "SELECT date, note_text FROM checkins "
        "WHERE note_text IS NOT NULL AND TRIM(note_text) != '' "
        "ORDER BY date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/journal/notes", response_class=HTMLResponse)
def notes_get(request: Request) -> HTMLResponse:
    with connect() as conn:
        notes = _load_notes(conn)
    return templates.TemplateResponse(request, "journal_notes.html", {
        "active_tab": "notes",
        "notes": notes,
    })


def _notes_list_response(request: Request, notes: list[dict]) -> HTMLResponse:
    return templates.TemplateResponse(request, "_notes_list.html", {"notes": notes})


@router.post("/journal/notes/{note_date}/edit", response_class=HTMLResponse)
async def notes_edit(request: Request, note_date: str,
                      note_text: str = Form(...)) -> HTMLResponse:
    _validate_date(note_date)
    txt = note_text.strip()
    if not txt:
        raise HTTPException(400, "note_text cannot be empty — use Clear instead")
    with connect() as conn:
        cur = conn.execute(
            "UPDATE checkins SET note_text = ? WHERE date = ?",
            (txt, note_date),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "no check-in for that date")
        notes = _load_notes(conn)
    return _notes_list_response(request, notes)


@router.post("/journal/notes/{note_date}/clear", response_class=HTMLResponse)
def notes_clear(request: Request, note_date: str) -> HTMLResponse:
    _validate_date(note_date)
    with connect() as conn:
        cur = conn.execute(
            "UPDATE checkins SET note_text = NULL WHERE date = ?",
            (note_date,),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "no check-in for that date")
        notes = _load_notes(conn)
    return _notes_list_response(request, notes)


# ---------- Backward compat: redirect old /trigger to /journal/triggers ----------

@router.get("/trigger")
def trigger_legacy_redirect():
    return RedirectResponse("/journal/triggers", status_code=308)
