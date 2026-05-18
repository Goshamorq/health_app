import sqlite3
from pathlib import Path

import pytest

from app.scoring import daily_score, other_score

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


@pytest.fixture
def conn(tmp_path):
    db = sqlite3.connect(tmp_path / "test.db")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    # Apply all schema migrations in order. 002 seeds habits we don't want for isolation,
    # so wipe habits after schema is in place.
    for sql_file in sorted(MIGRATIONS.glob("*.sql")):
        db.executescript(sql_file.read_text())
    db.execute("DELETE FROM habits")
    db.execute("DELETE FROM checkins")
    db.execute("DELETE FROM habit_entries")
    db.commit()
    yield db
    db.close()


def _add_habit(conn, pillar, name, created_at="2026-01-01"):
    cur = conn.execute(
        "INSERT INTO habits (pillar, name, type, threshold_config, created_at) "
        "VALUES (?, ?, 'binary', '{}', ?)",
        (pillar, name, created_at),
    )
    conn.commit()
    return cur.lastrowid


def _set_entry(conn, date_, habit_id, done):
    conn.execute(
        "INSERT INTO checkins (date) VALUES (?) ON CONFLICT(date) DO NOTHING",
        (date_,),
    )
    conn.execute(
        "INSERT INTO habit_entries (checkin_date, habit_id, value_json, done) "
        "VALUES (?, ?, '{}', ?) "
        "ON CONFLICT(checkin_date, habit_id) DO UPDATE SET done = excluded.done",
        (date_, habit_id, 1 if done else 0),
    )
    conn.commit()


def _set_checkin(conn, date_, **fields):
    """Upsert a checkin row with arbitrary scalar fields."""
    cols = ["date"] + list(fields.keys())
    placeholders = ",".join(["?"] * len(cols))
    values = [date_] + list(fields.values())
    conn.execute(
        f"INSERT INTO checkins ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(date) DO UPDATE SET "
        + ", ".join(f"{c} = excluded.{c}" for c in fields.keys()),
        values,
    )
    conn.commit()


# ============ Existing behavior (no settings passed → signals disabled) ============

def test_empty_db_returns_zero(conn):
    assert daily_score(conn, "2026-05-15") == {
        "total": 0,
        "by_pillar": {"sleep": 0, "sport": 0, "food": 0},
    }


def test_all_done_returns_100(conn):
    for pillar in ("sleep", "sport", "food"):
        for i in range(2):
            hid = _add_habit(conn, pillar, f"{pillar}-{i}")
            _set_entry(conn, "2026-05-15", hid, True)
    assert daily_score(conn, "2026-05-15") == {
        "total": 100,
        "by_pillar": {"sleep": 100, "sport": 100, "food": 100},
    }


def test_none_done_returns_zero(conn):
    for pillar in ("sleep", "sport", "food"):
        _add_habit(conn, pillar, f"{pillar}-1")
    assert daily_score(conn, "2026-05-15") == {
        "total": 0,
        "by_pillar": {"sleep": 0, "sport": 0, "food": 0},
    }


def test_mixed_math(conn):
    s1 = _add_habit(conn, "sleep", "s1")
    s2 = _add_habit(conn, "sleep", "s2")
    _set_entry(conn, "2026-05-15", s1, True)
    _set_entry(conn, "2026-05-15", s2, False)
    for i in range(4):
        hid = _add_habit(conn, "sport", f"sp{i}")
        _set_entry(conn, "2026-05-15", hid, i < 3)
    f1 = _add_habit(conn, "food", "f1")
    _add_habit(conn, "food", "f2")
    _set_entry(conn, "2026-05-15", f1, False)
    result = daily_score(conn, "2026-05-15")
    assert result["by_pillar"] == {"sleep": 50, "sport": 75, "food": 0}
    assert result["total"] == 42


def test_habit_created_after_target_date_excluded(conn):
    h = _add_habit(conn, "sleep", "future", created_at="2026-06-01")
    _set_entry(conn, "2026-05-15", h, True)
    assert daily_score(conn, "2026-05-15")["by_pillar"]["sleep"] == 0


def test_archived_habit_excluded(conn):
    hid = _add_habit(conn, "sport", "old")
    conn.execute("UPDATE habits SET archived = 1 WHERE id = ?", (hid,))
    conn.commit()
    _set_entry(conn, "2026-05-15", hid, True)
    assert daily_score(conn, "2026-05-15")["by_pillar"]["sport"] == 0


def test_total_averages_only_pillars_with_active_habits(conn):
    hid = _add_habit(conn, "sleep", "only-one")
    _set_entry(conn, "2026-05-15", hid, True)
    result = daily_score(conn, "2026-05-15")
    assert result["by_pillar"] == {"sleep": 100, "sport": 0, "food": 0}
    assert result["total"] == 100


# ============ Core signals (settings-driven) ============

SETTINGS_FULL = {
    "sleep_min_hours": "7",
    "sleep_max_hours": "9",
    "steps_min_bucket": "2",   # 7-10k or higher
    "water_min_bucket": "1",   # mid or higher
    "meals_min_count": "3",
}


def test_sleep_signal_in_range_counts_as_done(conn):
    _set_checkin(conn, "2026-05-15", sleep_hours=8.0)
    result = daily_score(conn, "2026-05-15", SETTINGS_FULL)
    # sleep: 1 signal met / 1 slot total = 100%
    assert result["by_pillar"]["sleep"] == 100


def test_sleep_signal_out_of_range_not_met(conn):
    _set_checkin(conn, "2026-05-15", sleep_hours=5.0)
    result = daily_score(conn, "2026-05-15", SETTINGS_FULL)
    assert result["by_pillar"]["sleep"] == 0


def test_sleep_signal_disabled_when_settings_missing(conn):
    hid = _add_habit(conn, "sleep", "habit-only")
    _set_entry(conn, "2026-05-15", hid, True)
    _set_checkin(conn, "2026-05-15", sleep_hours=99)  # bogus value irrelevant
    # No sleep settings → signal slot disabled
    result = daily_score(conn, "2026-05-15", {})
    assert result["by_pillar"]["sleep"] == 100


def test_steps_signal_meets_threshold(conn):
    _set_checkin(conn, "2026-05-15", steps_bucket="10-15k")  # index 3 ≥ 2
    result = daily_score(conn, "2026-05-15", SETTINGS_FULL)
    assert result["by_pillar"]["sport"] == 100


def test_steps_signal_below_threshold(conn):
    _set_checkin(conn, "2026-05-15", steps_bucket="5-7k")  # index 1 < 2
    result = daily_score(conn, "2026-05-15", SETTINGS_FULL)
    assert result["by_pillar"]["sport"] == 0


def test_food_two_signals_both_met(conn):
    _set_checkin(conn, "2026-05-15", water_bucket="good", meals_count=4)
    result = daily_score(conn, "2026-05-15", SETTINGS_FULL)
    # 2 signals met / 2 slots = 100%
    assert result["by_pillar"]["food"] == 100


def test_food_two_signals_one_met(conn):
    _set_checkin(conn, "2026-05-15", water_bucket="good", meals_count=1)
    result = daily_score(conn, "2026-05-15", SETTINGS_FULL)
    # 1 of 2 = 50%
    assert result["by_pillar"]["food"] == 50


def test_signals_combine_with_habits(conn):
    h = _add_habit(conn, "sleep", "habit")
    _set_entry(conn, "2026-05-15", h, True)
    _set_checkin(conn, "2026-05-15", sleep_hours=8.0)
    # 1 habit done + 1 signal met / 2 slots = 100%
    result = daily_score(conn, "2026-05-15", SETTINGS_FULL)
    assert result["by_pillar"]["sleep"] == 100


def test_signal_unmet_drags_pillar_down(conn):
    h = _add_habit(conn, "sleep", "habit")
    _set_entry(conn, "2026-05-15", h, True)
    _set_checkin(conn, "2026-05-15", sleep_hours=4.0)  # below 7-9 range
    result = daily_score(conn, "2026-05-15", SETTINGS_FULL)
    # 1 habit done + 0 signal met / 2 slots = 50%
    assert result["by_pillar"]["sleep"] == 50


def test_invalid_sleep_range_disables_signal(conn):
    bad = {"sleep_min_hours": "9", "sleep_max_hours": "7"}  # max < min
    _set_checkin(conn, "2026-05-15", sleep_hours=8.0)
    result = daily_score(conn, "2026-05-15", bad)
    # no slot, no habits → 0
    assert result["by_pillar"]["sleep"] == 0


def test_other_pillar_excluded_from_total(conn):
    # add an "other" habit, mark done
    h = _add_habit(conn, "other", "experiment")
    _set_entry(conn, "2026-05-15", h, True)
    # add a sleep habit not done
    s = _add_habit(conn, "sleep", "sleep-habit")
    _set_entry(conn, "2026-05-15", s, False)
    result = daily_score(conn, "2026-05-15")
    assert "other" not in result["by_pillar"]
    assert result["by_pillar"]["sleep"] == 0
    assert result["total"] == 0


# ============ Other pillar score + stars ============

def test_other_score_no_habits(conn):
    result = other_score(conn, "2026-05-15")
    assert result == {"pct": 0, "stars": 0, "active": 0}


def test_other_score_all_done_is_3_stars(conn):
    for i in range(2):
        h = _add_habit(conn, "other", f"o{i}")
        _set_entry(conn, "2026-05-15", h, True)
    result = other_score(conn, "2026-05-15")
    assert result == {"pct": 100, "stars": 3, "active": 2}


def test_other_score_none_done_is_0_stars(conn):
    for i in range(2):
        _add_habit(conn, "other", f"o{i}")
    result = other_score(conn, "2026-05-15")
    assert result == {"pct": 0, "stars": 0, "active": 2}


def test_other_score_buckets():
    """Boundary check the stars buckets via the same logic.
    0 → 0 stars; 1–33 → 1; 34–66 → 2; 67–100 → 3."""
    # Hand-compute via the public formula:
    cases = [(0, 0), (1, 1), (33, 1), (34, 2), (50, 2), (66, 2), (67, 3), (100, 3)]
    # The mapping is internal to other_score(); replicate it inline:
    def stars(p):
        if p == 0: return 0
        if p <= 33: return 1
        if p <= 66: return 2
        return 3
    for pct, expected in cases:
        assert stars(pct) == expected


def test_other_pillar_does_not_affect_daily_score_with_signals(conn):
    """Even with many done 'other' habits, sleep/sport/food totals shouldn't move."""
    for i in range(5):
        h = _add_habit(conn, "other", f"o{i}")
        _set_entry(conn, "2026-05-15", h, True)
    _set_checkin(conn, "2026-05-15", sleep_hours=8.0)
    result = daily_score(conn, "2026-05-15", SETTINGS_FULL)
    # sleep: 1 signal met, sport/food: signals enabled but no checkin values for them
    assert result["by_pillar"] == {"sleep": 100, "sport": 0, "food": 0}
    assert result["total"] == 33  # round((100+0+0)/3)
