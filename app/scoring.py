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
