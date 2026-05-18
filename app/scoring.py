import sqlite3

PILLARS = ("sleep", "sport", "food")


def daily_score(conn: sqlite3.Connection, target_date: str) -> dict:
    """Pillar = done_habits / active_habits_on_date * 100.
    Total = average over pillars that have at least one active habit.
    A habit is "active on date" if archived=0 and date(created_at) <= target_date.
    A habit with no habit_entries row counts as not-done."""
    by_pillar = {}
    pillars_with_active = []
    for pillar in PILLARS:
        row = conn.execute(
            """SELECT
                 COUNT(*) AS active,
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
        if active > 0:
            by_pillar[pillar] = int(round(100 * done / active))
            pillars_with_active.append(pillar)
        else:
            by_pillar[pillar] = 0
    if pillars_with_active:
        total = int(round(sum(by_pillar[p] for p in pillars_with_active) / len(pillars_with_active)))
    else:
        total = 0
    return {"total": total, "by_pillar": by_pillar}


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
