import sqlite3
from pathlib import Path

import pytest

from app.scoring import daily_score

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


@pytest.fixture
def conn(tmp_path):
    db = sqlite3.connect(tmp_path / "test.db")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript((MIGRATIONS / "001_init.sql").read_text())
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
    result = daily_score(conn, "2026-05-15")
    assert result == {
        "total": 100,
        "by_pillar": {"sleep": 100, "sport": 100, "food": 100},
    }


def test_none_done_returns_zero(conn):
    for pillar in ("sleep", "sport", "food"):
        _add_habit(conn, pillar, f"{pillar}-1")
    result = daily_score(conn, "2026-05-15")
    assert result == {
        "total": 0,
        "by_pillar": {"sleep": 0, "sport": 0, "food": 0},
    }


def test_mixed_math(conn):
    # sleep: 2 active, 1 done -> 50%
    s1 = _add_habit(conn, "sleep", "s1")
    s2 = _add_habit(conn, "sleep", "s2")
    _set_entry(conn, "2026-05-15", s1, True)
    _set_entry(conn, "2026-05-15", s2, False)
    # sport: 4 active, 3 done -> 75%
    for i in range(4):
        hid = _add_habit(conn, "sport", f"sp{i}")
        _set_entry(conn, "2026-05-15", hid, i < 3)
    # food: 2 active, 0 done (one explicit not-done, one missing entry) -> 0%
    f1 = _add_habit(conn, "food", "f1")
    _add_habit(conn, "food", "f2")
    _set_entry(conn, "2026-05-15", f1, False)
    result = daily_score(conn, "2026-05-15")
    assert result["by_pillar"] == {"sleep": 50, "sport": 75, "food": 0}
    # total = round((50 + 75 + 0) / 3) -> python banker's round picks 42
    assert result["total"] == 42


def test_habit_created_after_target_date_excluded(conn):
    # habit created on 2026-06-01 should be invisible on 2026-05-15
    h = _add_habit(conn, "sleep", "future", created_at="2026-06-01")
    _set_entry(conn, "2026-05-15", h, True)
    result = daily_score(conn, "2026-05-15")
    assert result["by_pillar"]["sleep"] == 0


def test_archived_habit_excluded(conn):
    hid = _add_habit(conn, "sport", "old")
    conn.execute("UPDATE habits SET archived = 1 WHERE id = ?", (hid,))
    conn.commit()
    _set_entry(conn, "2026-05-15", hid, True)
    result = daily_score(conn, "2026-05-15")
    assert result["by_pillar"]["sport"] == 0


def test_total_averages_only_pillars_with_active_habits(conn):
    # only sleep pillar has habits -> total == sleep score, not diluted by zeros
    hid = _add_habit(conn, "sleep", "only-one")
    _set_entry(conn, "2026-05-15", hid, True)
    result = daily_score(conn, "2026-05-15")
    assert result["by_pillar"] == {"sleep": 100, "sport": 0, "food": 0}
    assert result["total"] == 100
