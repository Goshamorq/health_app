PRAGMA foreign_keys = OFF;

CREATE TABLE habits_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pillar TEXT NOT NULL CHECK(pillar IN ('sleep', 'sport', 'food', 'other')),
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('binary', 'time', 'quantity')),
    threshold_config TEXT NOT NULL DEFAULT '{}',
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO habits_new (id, pillar, name, type, threshold_config, archived, created_at)
    SELECT id, pillar, name, type, threshold_config, archived, created_at FROM habits;

DROP TABLE habits;
ALTER TABLE habits_new RENAME TO habits;

PRAGMA foreign_keys = ON;
