CREATE TABLE goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    reward TEXT,
    punishment TEXT,
    deadline TEXT NOT NULL,                          -- ISO date YYYY-MM-DD
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft','active','completed','failed','archived')),
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    activated_at TEXT,
    closed_at TEXT,
    closing_note TEXT
);

-- Enforce: at most one goal in status='active' at any time.
CREATE UNIQUE INDEX idx_goals_one_active
    ON goals(status) WHERE status = 'active';
