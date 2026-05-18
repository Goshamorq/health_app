from datetime import date as date_cls, timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.db import connect
from app.scoring import daily_score, other_score, streaks_for_active_habits

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


def _heatmap_level(pct: int) -> int:
    if pct == 0:
        return 0
    if pct <= 33:
        return 1
    if pct <= 66:
        return 2
    return 3


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, date: str | None = None) -> HTMLResponse:
    today = date_cls.today()
    today_iso = today.isoformat()
    yesterday_iso = (today - timedelta(days=1)).isoformat()

    if date:
        try:
            target_date = date_cls.fromisoformat(date).isoformat()
        except ValueError:
            target_date = today_iso
    else:
        target_date = today_iso
    is_today = target_date == today_iso

    with connect() as conn:
        settings = {r["key"]: r["value"]
                    for r in conn.execute("SELECT key, value FROM settings").fetchall()}
        score = daily_score(conn, target_date, settings)
        other = other_score(conn, target_date)
        # Streaks are always "as of now", regardless of which day the dashboard views
        streaks = streaks_for_active_habits(conn, today_iso, settings)
        has_target_checkin = conn.execute(
            "SELECT EXISTS(SELECT 1 FROM checkins WHERE date = ?)", (target_date,)
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
            o = other_score(conn, d_iso)
            week.append({
                "date": d_iso,
                "weekday": WEEKDAY_SHORT[d.weekday()],
                "score": s["total"],
                "band": _score_band(s["total"]),
                "is_viewed": d_iso == target_date,
                "other_stars": o["stars"],
                "other_active": o["active"],
            })

        # 30-day heatmap: 4 pillar rows × 30 day cells
        heatmap_by_date = []
        for offset in range(29, -1, -1):
            d = today - timedelta(days=offset)
            d_iso = d.isoformat()
            s = daily_score(conn, d_iso, settings)
            o = other_score(conn, d_iso)
            heatmap_by_date.append({
                "date": d_iso,
                "by_pillar": {**s["by_pillar"], "other": o["pct"]},
            })
        heatmap_rows = []
        for pillar in ("sleep", "sport", "food", "other"):
            cells = [{
                "date": day["date"],
                "pct": day["by_pillar"][pillar],
                "level": _heatmap_level(day["by_pillar"][pillar]),
                "is_viewed": day["date"] == target_date,
            } for day in heatmap_by_date]
            heatmap_rows.append({"pillar": pillar, "cells": cells})

    show_yesterday_prompt = (
        is_today
        and bool(has_prior_to_yesterday)
        and not bool(has_yesterday_checkin)
    )

    return templates.TemplateResponse(request, "dashboard.html", {
        "score": score,
        "score_band": _score_band(score["total"]),
        "other": other,
        "streaks": streaks,
        "is_today": is_today,
        "target_date": target_date,
        "today_iso": today_iso,
        "yesterday_iso": yesterday_iso,
        "has_target_checkin": bool(has_target_checkin),
        "show_yesterday_prompt": show_yesterday_prompt,
        "week": week,
        "heatmap_rows": heatmap_rows,
    })
