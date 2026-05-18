import sqlite3

SCORED_PILLARS = ("sleep", "sport", "food")
ALL_PILLARS = (*SCORED_PILLARS, "other")

STEPS_BUCKETS = ("<5k", "5-7k", "7-10k", "10-15k", "15k+")
WATER_BUCKETS = ("low", "mid", "good")


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


def _signal_slots(pillar: str, settings: dict, checkin_row) -> list[bool]:
    """For each ENABLED core signal in this pillar, return whether it's met.
    A signal is enabled only when its settings threshold parses to a valid value."""
    slots: list[bool] = []
    if pillar == "sleep":
        mn = _parse_float(settings.get("sleep_min_hours"))
        mx = _parse_float(settings.get("sleep_max_hours"))
        if mn is not None and mx is not None and mn <= mx:
            sh = checkin_row["sleep_hours"] if checkin_row is not None and checkin_row["sleep_hours"] is not None else None
            slots.append(sh is not None and mn <= sh <= mx)
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
                 AND date(h.created_at) <= ?
                 AND h.pillar = ?""",
            (target_date, target_date, pillar),
        ).fetchone()
        active = row["active"] or 0
        done = row["done"] or 0
        signals = _signal_slots(pillar, settings, checkin_row)
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
             AND date(h.created_at) <= ?
             AND h.pillar = 'other'""",
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
