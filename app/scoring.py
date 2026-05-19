import sqlite3
import statistics
from datetime import date as date_cls, timedelta

SCORED_PILLARS = ("sleep", "sport", "food")
ALL_PILLARS = (*SCORED_PILLARS, "other")

STEPS_BUCKETS = ("<5k", "5-7k", "7-10k", "10-15k", "15k+")
WATER_BUCKETS = ("<1", "1-1.5", "1.5-2", "2+")


def _parse_int(s, default=None):
    if s in (None, ""):
        return default
    try:
        return int(s)
    except (TypeError, ValueError):
        return default


def _parse_float(s, default=None):
    if s in (None, ""):
        return default
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def _bedtime_to_minutes(s) -> float | None:
    """HH:MM → minutes since midnight, with 00:00-11:59 shifted +24h so that
    late-night bedtimes (23:30, 00:30) sit on a continuous scale."""
    if not s:
        return None
    try:
        hh, mm = str(s).split(":")
        m = int(hh) * 60 + int(mm)
    except (ValueError, AttributeError, TypeError):
        return None
    if m < 12 * 60:
        m += 24 * 60
    return float(m)


def _bedtime_regularity(conn: sqlite3.Connection, target_date: str, settings: dict) -> bool | None:
    """True if std-dev of bedtimes in last 7 days ≤ threshold AND ≥ min_samples
    were logged. Returns None when the signal is disabled (threshold unset or
    too few samples to judge)."""
    std_max = _parse_float(settings.get("sleep_bedtime_std_max_min"))
    min_samp = _parse_int(settings.get("sleep_min_bedtime_samples"))
    if std_max is None or min_samp is None:
        return None
    end = date_cls.fromisoformat(target_date)
    start = end - timedelta(days=6)
    rows = conn.execute(
        "SELECT bedtime FROM checkins "
        "WHERE date BETWEEN ? AND ? AND bedtime IS NOT NULL AND bedtime != ''",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    times: list[float] = []
    for r in rows:
        m = _bedtime_to_minutes(r["bedtime"])
        if m is not None:
            times.append(m)
    if len(times) < min_samp:
        return None
    return statistics.pstdev(times) <= std_max


def _signal_slots(pillar: str, settings: dict, checkin_row,
                  bedtime_regular: bool | None = None) -> list[bool]:
    """For each ENABLED core signal in this pillar, return whether it's met.
    A signal is enabled only when its settings threshold parses to a valid value.
    For sleep, `bedtime_regular` is a pre-computed True/False/None — None means
    the regularity signal is disabled and no slot is added."""
    slots: list[bool] = []
    if pillar == "sleep":
        mn = _parse_float(settings.get("sleep_min_hours"))
        mx = _parse_float(settings.get("sleep_max_hours"))
        if mn is not None and mx is not None and mn <= mx:
            sh = checkin_row["sleep_hours"] if checkin_row is not None and checkin_row["sleep_hours"] is not None else None
            slots.append(sh is not None and mn <= sh <= mx)
        if bedtime_regular is not None:
            slots.append(bedtime_regular)
    elif pillar == "sport":
        thr = _parse_int(settings.get("steps_min_bucket"))
        if thr is not None and 0 <= thr < len(STEPS_BUCKETS):
            sb = checkin_row["steps_bucket"] if checkin_row is not None else None
            slots.append(sb in STEPS_BUCKETS and STEPS_BUCKETS.index(sb) >= thr)
    elif pillar == "food":
        thr_w = _parse_int(settings.get("water_min_bucket"))
        if thr_w is not None and 0 <= thr_w < len(WATER_BUCKETS):
            wb = checkin_row["water_bucket"] if checkin_row is not None else None
            slots.append(wb in WATER_BUCKETS and WATER_BUCKETS.index(wb) >= thr_w)
        thr_m = _parse_int(settings.get("meals_min_count"))
        if thr_m is not None:
            mc = None
            if checkin_row is not None and "meals_count" in checkin_row.keys():
                mc = checkin_row["meals_count"]
            slots.append(mc is not None and mc >= thr_m)
    return slots


def daily_score(conn: sqlite3.Connection, target_date: str, settings: dict | None = None) -> dict:
    """Pillar score combines core signals (from global checkin fields, gated by settings)
    with active habits. Total = mean over pillars with at least one slot.
    The 'other' pillar is excluded from totals — query separately via other_score()."""
    settings = settings or {}
    checkin_row = conn.execute("SELECT * FROM checkins WHERE date = ?", (target_date,)).fetchone()
    bedtime_regular = _bedtime_regularity(conn, target_date, settings)
    by_pillar: dict[str, int] = {}
    pillars_with_data: list[str] = []
    for pillar in SCORED_PILLARS:
        row = conn.execute(
            """SELECT COUNT(*) AS active,
                      COALESCE(SUM(CASE WHEN he.done = 1 THEN 1 ELSE 0 END), 0) AS done
               FROM habits h
               LEFT JOIN habit_entries he
                 ON he.habit_id = h.id AND he.checkin_date = ?
               WHERE h.archived = 0
                 AND h.pillar = ?
                 AND (date(h.created_at) <= ? OR he.checkin_date IS NOT NULL)""",
            (target_date, pillar, target_date),
        ).fetchone()
        active = row["active"] or 0
        done = row["done"] or 0
        signals = _signal_slots(pillar, settings, checkin_row, bedtime_regular=bedtime_regular)
        denom = active + len(signals)
        numer = done + sum(1 for s in signals if s)
        if denom > 0:
            by_pillar[pillar] = int(round(100 * numer / denom))
            pillars_with_data.append(pillar)
        else:
            by_pillar[pillar] = 0
    total = (
        int(round(sum(by_pillar[p] for p in pillars_with_data) / len(pillars_with_data)))
        if pillars_with_data
        else 0
    )
    return {"total": total, "by_pillar": by_pillar}


def other_score(conn: sqlite3.Connection, target_date: str) -> dict:
    """Returns {pct, stars, active}. Stars: 0 if pct == 0, 1 if 1-33, 2 if 34-66, 3 if 67+."""
    row = conn.execute(
        """SELECT COUNT(*) AS active,
                  COALESCE(SUM(CASE WHEN he.done = 1 THEN 1 ELSE 0 END), 0) AS done
           FROM habits h
           LEFT JOIN habit_entries he
             ON he.habit_id = h.id AND he.checkin_date = ?
           WHERE h.archived = 0
             AND h.pillar = 'other'
             AND (date(h.created_at) <= ? OR he.checkin_date IS NOT NULL)""",
        (target_date, target_date),
    ).fetchone()
    active = row["active"] or 0
    done = row["done"] or 0
    pct = int(round(100 * done / active)) if active > 0 else 0
    if pct == 0:
        stars = 0
    elif pct <= 33:
        stars = 1
    elif pct <= 66:
        stars = 2
    else:
        stars = 3
    return {"pct": pct, "stars": stars, "active": active}


def streak(conn: sqlite3.Connection, habit_id: int, today: str,
           allowed_misses_per_7: int = 0) -> int:
    """Days of current streak walking back from `today`. Forgiveness:
    at each walking step, the rolling 7-day window of last walked days
    may contain up to `allowed_misses_per_7` misses; once that count is
    exceeded the streak ends. A miss is `done=0` or no habit_entries row.
    Set allowed_misses_per_7=0 for classic (any miss breaks)."""
    h = conn.execute(
        "SELECT date(created_at) AS d FROM habits WHERE id = ?",
        (habit_id,),
    ).fetchone()
    if h is None:
        return 0
    # Walk floor: min(created_at, oldest backfilled entry) so retro-logging
    # past dates extends the reachable streak.
    oldest_entry = conn.execute(
        "SELECT MIN(checkin_date) AS d FROM habit_entries WHERE habit_id = ?",
        (habit_id,),
    ).fetchone()["d"]
    earliest = h["d"]
    if oldest_entry is not None and oldest_entry < earliest:
        earliest = oldest_entry

    days = 0
    seen_done = False
    window: list[bool] = []  # True = miss; newest at front
    d = date_cls.fromisoformat(today)
    while d.isoformat() >= earliest:
        row = conn.execute(
            "SELECT done FROM habit_entries WHERE habit_id = ? AND checkin_date = ?",
            (habit_id, d.isoformat()),
        ).fetchone()
        is_miss = row is None or not bool(row["done"])
        window.insert(0, is_miss)
        if len(window) > 7:
            window.pop()
        if sum(1 for m in window if m) > allowed_misses_per_7:
            break
        days += 1
        if not is_miss:
            seen_done = True
        d -= timedelta(days=1)
    # Forgiveness shouldn't manufacture a streak out of pure inactivity.
    return days if seen_done else 0


def streaks_for_active_habits(conn: sqlite3.Connection, today: str,
                              settings: dict | None = None) -> list[dict]:
    """Streak per active habit, ordered by pillar then id, for dashboard."""
    settings = settings or {}
    enabled = settings.get("streak_forgiveness_enabled", "1") == "1"
    threshold = 0
    if enabled:
        try:
            threshold = max(0, int(settings.get("streak_forgiveness_threshold") or "0"))
        except (TypeError, ValueError):
            threshold = 0

    pillar_order = {p: i for i, p in enumerate(ALL_PILLARS)}
    rows = conn.execute(
        "SELECT id, pillar, name FROM habits "
        "WHERE archived = 0 AND date(created_at) <= ? "
        "ORDER BY pillar, id",
        (today,),
    ).fetchall()
    out = []
    for r in rows:
        out.append({
            "habit_id": r["id"],
            "pillar": r["pillar"],
            "name": r["name"],
            "streak": streak(conn, r["id"], today, allowed_misses_per_7=threshold),
        })
    out.sort(key=lambda s: (pillar_order.get(s["pillar"], 99), -s["streak"], s["habit_id"]))
    return out


def is_done(habit_type: str, threshold: dict, value: dict) -> bool:
    if habit_type == "binary":
        return bool(value.get("checked"))
    if habit_type == "time":
        t = value.get("time")
        if not t:
            return False
        target = threshold.get("target")
        direction = threshold.get("direction", "before")
        if not target:
            return False
        return t <= target if direction == "before" else t >= target
    if habit_type == "quantity":
        bucket = value.get("bucket")
        if bucket is None:
            return False
        return int(bucket) >= int(threshold.get("min_done_bucket", 0))
    return False


def parse_habit_input(habit_type: str, raw: str | None) -> dict:
    if habit_type == "binary":
        return {"checked": raw in ("1", "on", "true")}
    if habit_type == "time":
        return {"time": raw or None}
    if habit_type == "quantity":
        if raw in (None, ""):
            return {"bucket": None}
        try:
            return {"bucket": int(raw)}
        except (TypeError, ValueError):
            return {"bucket": None}
    return {}
