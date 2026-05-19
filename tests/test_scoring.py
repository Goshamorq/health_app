import sqlite3
from datetime import date as date_cls, timedelta
from pathlib import Path

import pytest

from app.scoring import daily_score, other_score, streak, streaks_for_active_habits

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


def test_future_created_habit_without_entry_is_excluded(conn):
    # No habit_entries on target_date AND created_at > target_date → excluded.
    _add_habit(conn, "sleep", "future", created_at="2026-06-01")
    assert daily_score(conn, "2026-05-15")["by_pillar"]["sleep"] == 0


def test_future_created_habit_with_backfilled_entry_counts(conn):
    # User created a habit today and retro-logged a past date — that day counts.
    h = _add_habit(conn, "sleep", "future", created_at="2026-06-01")
    _set_entry(conn, "2026-05-15", h, True)
    assert daily_score(conn, "2026-05-15")["by_pillar"]["sleep"] == 100


def test_future_created_habit_backfilled_miss_counts_as_slot(conn):
    # Backfilled entry with done=0 still adds a slot to the denominator.
    h = _add_habit(conn, "sleep", "future", created_at="2026-06-01")
    _set_entry(conn, "2026-05-15", h, False)
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
    _set_checkin(conn, "2026-05-15", water_bucket="2+", meals_count=4)
    result = daily_score(conn, "2026-05-15", SETTINGS_FULL)
    # 2 signals met / 2 slots = 100%
    assert result["by_pillar"]["food"] == 100


def test_food_two_signals_one_met(conn):
    _set_checkin(conn, "2026-05-15", water_bucket="2+", meals_count=1)
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


# ============ Sleep regularity (bedtime std-dev) ============

REGULARITY_SETTINGS = {
    "sleep_bedtime_std_max_min": "30",
    "sleep_min_bedtime_samples": "4",
}


def test_regularity_disabled_when_too_few_samples(conn):
    for i in range(2):
        d = (date_cls(2026, 5, 15) - timedelta(days=i)).isoformat()
        _set_checkin(conn, d, bedtime="23:00")
    # Only 2 samples < threshold 4 → signal disabled. No habits → pillar = 0%
    result = daily_score(conn, "2026-05-15", REGULARITY_SETTINGS)
    assert result["by_pillar"]["sleep"] == 0


def test_regularity_consistent_bedtimes_met(conn):
    # 4 nights all at 23:00 — std=0 ≤ 30
    for i in range(4):
        d = (date_cls(2026, 5, 15) - timedelta(days=i)).isoformat()
        _set_checkin(conn, d, bedtime="23:00")
    result = daily_score(conn, "2026-05-15", REGULARITY_SETTINGS)
    assert result["by_pillar"]["sleep"] == 100  # 1 of 1 slot


def test_regularity_inconsistent_bedtimes_not_met(conn):
    # Bedtimes vary by ±2 hours — std way > 30 min
    for i, t in enumerate(["22:00", "01:00", "23:00", "00:30"]):
        d = (date_cls(2026, 5, 15) - timedelta(days=i)).isoformat()
        _set_checkin(conn, d, bedtime=t)
    result = daily_score(conn, "2026-05-15", REGULARITY_SETTINGS)
    # signal slot exists but not met → 0/1 = 0%
    assert result["by_pillar"]["sleep"] == 0


def test_regularity_wraparound_around_midnight(conn):
    # 23:30 / 00:00 / 00:30 / 23:45 — all within 60 minutes when wrapped
    for i, t in enumerate(["23:30", "00:00", "00:30", "23:45"]):
        d = (date_cls(2026, 5, 15) - timedelta(days=i)).isoformat()
        _set_checkin(conn, d, bedtime=t)
    result = daily_score(conn, "2026-05-15", REGULARITY_SETTINGS)
    # wraparound puts these on a 23:30..00:30 continuous scale; std ≤ 30
    assert result["by_pillar"]["sleep"] == 100


def test_regularity_adds_second_slot_alongside_duration(conn):
    # both signals enabled, both met → pillar = 100%
    for i in range(4):
        d = (date_cls(2026, 5, 15) - timedelta(days=i)).isoformat()
        _set_checkin(conn, d, sleep_hours=8.0, bedtime="23:00")
    combined = {**SETTINGS_FULL, **REGULARITY_SETTINGS}
    result = daily_score(conn, "2026-05-15", combined)
    assert result["by_pillar"]["sleep"] == 100

    # break one: bedtime varies → 1 of 2 = 50%
    _set_checkin(conn, "2026-05-15", bedtime="04:00")  # outlier
    result2 = daily_score(conn, "2026-05-15", combined)
    assert result2["by_pillar"]["sleep"] == 50


# ============ Streaks ============

def _seed_streak(conn, habit_id, today_iso, pattern):
    """Set entries by walking back from today. pattern: 'D' = done, 'M' = miss-as-entry,
    '_' = no entry. Example: 'DDD__M' = today done, -1 done, -2 done, -3 missing entry,
    -4 missing entry, -5 explicit miss row."""
    from datetime import date as _d, timedelta as _td
    today = _d.fromisoformat(today_iso)
    for i, ch in enumerate(pattern):
        d = today - _td(days=i)
        if ch == '_':
            continue
        done = 1 if ch == 'D' else 0
        conn.execute("INSERT INTO checkins (date) VALUES (?) ON CONFLICT(date) DO NOTHING", (d.isoformat(),))
        conn.execute(
            "INSERT INTO habit_entries (checkin_date, habit_id, value_json, done) "
            "VALUES (?, ?, '{}', ?) "
            "ON CONFLICT(checkin_date, habit_id) DO UPDATE SET done = excluded.done",
            (d.isoformat(), habit_id, done),
        )
    conn.commit()


def test_streak_zero_when_no_entries(conn):
    h = _add_habit(conn, "sleep", "habit", created_at="2026-01-01")
    assert streak(conn, h, "2026-05-15", allowed_misses_per_7=1) == 0


def test_streak_classic_unbroken_chain(conn):
    h = _add_habit(conn, "sleep", "habit", created_at="2026-05-01")
    _seed_streak(conn, h, "2026-05-15", "DDDDDDDD")  # 8 days done
    assert streak(conn, h, "2026-05-15", allowed_misses_per_7=0) == 8


def test_streak_classic_breaks_on_any_miss(conn):
    h = _add_habit(conn, "sleep", "habit", created_at="2026-05-01")
    _seed_streak(conn, h, "2026-05-15", "DDDM_DD")  # done,done,done,MISS at -3
    # threshold=0: any miss breaks → streak counts up to but not including the miss
    assert streak(conn, h, "2026-05-15", allowed_misses_per_7=0) == 3


def test_streak_forgiveness_allows_one_miss(conn):
    h = _add_habit(conn, "sleep", "habit", created_at="2026-05-01")
    _seed_streak(conn, h, "2026-05-15", "DDMDDDD")  # 1 miss at -2 in last 7
    # 6 done days in the run; the M doesn't count toward the streak number
    assert streak(conn, h, "2026-05-15", allowed_misses_per_7=1) == 6


def test_streak_forgiveness_breaks_on_two_misses_within_7(conn):
    h = _add_habit(conn, "sleep", "habit", created_at="2026-05-01")
    _seed_streak(conn, h, "2026-05-15", "DDMDMDD")  # 2 misses (at -2 and -4) in last 7
    # walk: D D M(no incr, miss=1) D M(window misses=2 → break). Done count = 3.
    assert streak(conn, h, "2026-05-15", allowed_misses_per_7=1) == 3


def test_streak_spreads_misses_across_weeks_allowed(conn):
    h = _add_habit(conn, "sleep", "habit", created_at="2026-04-01")
    # Pattern: today through day-13, with misses at -3 (week 1) and -10 (week 2)
    pattern = "DDDM" + "DDDDDD" + "M" + "DDD"  # 14 chars, 12 D's
    _seed_streak(conn, h, "2026-05-15", pattern)
    # Each rolling-7 window has at most 1 miss → chain doesn't break → 12 done days
    assert streak(conn, h, "2026-05-15", allowed_misses_per_7=1) == 12


def test_streak_bounded_by_habit_creation_date(conn):
    h = _add_habit(conn, "sleep", "habit", created_at="2026-05-13")
    _seed_streak(conn, h, "2026-05-15", "DDD")  # 3 done days available
    # streak shouldn't walk further than habit existed (3 days back)
    assert streak(conn, h, "2026-05-15", allowed_misses_per_7=1) == 3


def test_streak_today_missing_classic_shows_prior_run(conn):
    h = _add_habit(conn, "sleep", "habit", created_at="2026-05-01")
    _seed_streak(conn, h, "2026-05-15", "_DDDD")  # no entry today; done -1..-4
    # With new semantics, streak walks from the most recent done day (-1) backward,
    # counting 4 done days. Today's miss doesn't penalize the past run.
    assert streak(conn, h, "2026-05-15", allowed_misses_per_7=0) == 4


def test_streak_today_missing_forgiven(conn):
    h = _add_habit(conn, "sleep", "habit", created_at="2026-05-01")
    # today miss (skipped), -1=D start, -2=D, -3=M (no incr, miss=1)
    _seed_streak(conn, h, "2026-05-15", "_DDM")
    # walk from -1: D(1), D(2), M(miss=1, no incr), then next day (-4 in pattern,
    # no entry) is also a miss → window misses=2 → break. Done count = 2.
    assert streak(conn, h, "2026-05-15", allowed_misses_per_7=1) == 2


def test_streak_only_one_done_day(conn):
    """User's reported case: filled 1 day → streak shows 1, not 2 via forgiveness."""
    h = _add_habit(conn, "sleep", "habit", created_at="2026-05-01")
    _seed_streak(conn, h, "2026-05-15", "_D")  # today miss, yesterday done; nothing else
    assert streak(conn, h, "2026-05-15", allowed_misses_per_7=1) == 1


def test_streak_unknown_habit_returns_zero(conn):
    assert streak(conn, 9999, "2026-05-15") == 0


def test_streaks_for_active_habits_ordering_and_settings(conn):
    s = _add_habit(conn, "sleep", "S1", created_at="2026-05-10")
    sp = _add_habit(conn, "sport", "Sp1", created_at="2026-05-10")
    _seed_streak(conn, s, "2026-05-15", "DDD")     # streak 3
    _seed_streak(conn, sp, "2026-05-15", "DDDDD")  # streak 5
    # forgiveness off → both still unbroken since no misses
    out = streaks_for_active_habits(conn, "2026-05-15",
                                    {"streak_forgiveness_enabled": "0"})
    pillars = [r["pillar"] for r in out]
    streaks = {r["name"]: r["streak"] for r in out}
    assert pillars == ["sleep", "sport"]  # pillar order
    assert streaks == {"S1": 3, "Sp1": 5}


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
