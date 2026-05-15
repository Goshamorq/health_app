import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "health.db"
MIGRATIONS_DIR = ROOT / "migrations"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_migrations() -> list[int]:
    applied_now: list[int] = []
    conn = connect()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "version INTEGER PRIMARY KEY, "
            "applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        current = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]
        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = int(sql_file.name.split("_", 1)[0])
            if version <= current:
                continue
            conn.executescript(sql_file.read_text())
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
            conn.commit()
            applied_now.append(version)
    finally:
        conn.close()
    return applied_now
