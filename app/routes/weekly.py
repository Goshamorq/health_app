from datetime import date as date_cls, timedelta
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db import connect
from app.scoring import daily_score

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=ROOT / "app" / "templates")
router = APIRouter()


def _week_start(d: date_cls) -> date_cls:
    return d - timedelta(days=d.weekday())  # Monday


def _round_or_none(v, ndigits=1):
    return round(v, ndigits) if v is not None else None


@router.get("/weekly", response_class=HTMLResponse)
def weekly_get(request: Request, week: str | None = None):
    today = date_cls.today()
    current_monday = _week_start(today)

    if week:
        try:
            monday = _week_start(date_cls.fromisoformat(week))
        except ValueError:
            monday = current_monday
    else:
        monday = current_monday

    # Clamp future weeks to current
    if monday > current_monday:
        return RedirectResponse(f"/weekly?week={current_monday.isoformat()}", status_code=303)

    sunday = monday + timedelta(days=6)
    days_iso = [(monday + timedelta(days=i)).isoformat() for i in range(7)]
    is_current = monday == current_monday

    with connect() as conn:
        settings = {r["key"]: r["value"]
                    for r in conn.execute("SELECT key, value FROM settings").fetchall()}
        scores = [daily_score(conn, d_iso, settings)["total"] for d_iso in days_iso]
        score_avg = round(sum(scores) / 7)
        good_days = sum(1 for s in scores if s >= 67)

        agg = conn.execute(
            """SELECT
                 AVG(sleep_hours) AS avg_sleep,
                 AVG(mood_am)     AS avg_mood_am,
                 AVG(mood_pm)     AS avg_mood_pm,
                 AVG(meals_count) AS avg_meals,
                 COUNT(*) AS checkin_days
               FROM checkins WHERE date BETWEEN ? AND ?""",
            (days_iso[0], days_iso[-1]),
        ).fetchone()

        trigger_count = conn.execute(
            "SELECT COUNT(*) AS c FROM trigger_entries "
            "WHERE date(ts, 'localtime') BETWEEN ? AND ?",
            (days_iso[0], days_iso[-1]),
        ).fetchone()["c"]

        review = conn.execute(
            "SELECT notes_text FROM weekly_reviews WHERE week_start_date = ?",
            (monday.isoformat(),),
        ).fetchone()
        notes = review["notes_text"] if review and review["notes_text"] else ""

    return templates.TemplateResponse(request, "weekly.html", {
        "monday": monday.isoformat(),
        "sunday": sunday.isoformat(),
        "prev_week": (monday - timedelta(days=7)).isoformat(),
        "next_week": (monday + timedelta(days=7)).isoformat(),
        "is_current": is_current,
        "score_avg": score_avg,
        "good_days": good_days,
        "checkin_days": agg["checkin_days"] or 0,
        "avg_sleep":   _round_or_none(agg["avg_sleep"]),
        "avg_mood_am": _round_or_none(agg["avg_mood_am"]),
        "avg_mood_pm": _round_or_none(agg["avg_mood_pm"]),
        "avg_meals":   _round_or_none(agg["avg_meals"]),
        "trigger_count": trigger_count or 0,
        "notes": notes,
        "saved": request.query_params.get("saved") == "1",
    })


@router.post("/weekly")
async def weekly_post(week_start_date: str = Form(...),
                       notes_text: str = Form("")) -> RedirectResponse:
    try:
        d = date_cls.fromisoformat(week_start_date)
    except ValueError:
        raise HTTPException(400, "invalid week_start_date")
    monday = _week_start(d)
    notes = notes_text.strip() or None
    with connect() as conn:
        conn.execute(
            "INSERT INTO weekly_reviews (week_start_date, notes_text, updated_at) "
            "VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(week_start_date) DO UPDATE SET "
            "notes_text = excluded.notes_text, updated_at = datetime('now')",
            (monday.isoformat(), notes),
        )
    return RedirectResponse(f"/weekly?week={monday.isoformat()}&saved=1", status_code=303)
