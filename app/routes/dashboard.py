from datetime import date as date_cls, timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.db import connect
from app.scoring import daily_score

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=ROOT / "app" / "templates")
router = APIRouter()

WEEKDAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _score_band(score: int) -> str:
    if score >= 67:
        return "is-good"
    if score >= 34:
        return "is-mid"
    if score >= 1:
        return "is-bad"
    return "is-empty"


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    today = date_cls.today()
    today_iso = today.isoformat()
    yesterday = today - timedelta(days=1)
    yesterday_iso = yesterday.isoformat()

    with connect() as conn:
        settings = {r["key"]: r["value"]
                    for r in conn.execute("SELECT key, value FROM settings").fetchall()}
        score = daily_score(conn, today_iso, settings)
        has_today_checkin = conn.execute(
            "SELECT EXISTS(SELECT 1 FROM checkins WHERE date = ?)", (today_iso,)
        ).fetchone()[0]
        has_yesterday_checkin = conn.execute(
            "SELECT EXISTS(SELECT 1 FROM checkins WHERE date = ?)", (yesterday_iso,)
        ).fetchone()[0]
        has_prior_to_yesterday = conn.execute(
            "SELECT EXISTS(SELECT 1 FROM checkins WHERE date < ?)", (yesterday_iso,)
        ).fetchone()[0]

        week = []
        for offset in range(6, -1, -1):
            d = today - timedelta(days=offset)
            d_iso = d.isoformat()
            s = daily_score(conn, d_iso, settings)
            week.append({
                "date": d_iso,
                "weekday": WEEKDAY_SHORT[d.weekday()],
                "score": s["total"],
                "band": _score_band(s["total"]),
                "is_today": offset == 0,
            })

    show_yesterday_prompt = bool(has_prior_to_yesterday) and not bool(has_yesterday_checkin)

    return templates.TemplateResponse(request, "dashboard.html", {
        "score": score,
        "score_band": _score_band(score["total"]),
        "has_today_checkin": bool(has_today_checkin),
        "today_iso": today_iso,
        "yesterday_iso": yesterday_iso,
        "show_yesterday_prompt": show_yesterday_prompt,
        "week": week,
    })
