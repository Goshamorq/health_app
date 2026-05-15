CREATE TABLE habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pillar TEXT NOT NULL CHECK(pillar IN ('sleep', 'sport', 'food')),
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('binary', 'time', 'quantity')),
    threshold_config TEXT NOT NULL DEFAULT '{}',
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE checkins (
    date TEXT PRIMARY KEY,
    sleep_hours REAL,
    sleep_quality INTEGER,
    mood_am INTEGER,
    mood_pm INTEGER,
    water_bucket TEXT,
    steps_bucket TEXT,
    caffeine INTEGER NOT NULL DEFAULT 0,
    alcohol INTEGER NOT NULL DEFAULT 0,
    late_meal INTEGER NOT NULL DEFAULT 0,
    food_text TEXT,
    note_text TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE habit_entries (
    checkin_date TEXT NOT NULL,
    habit_id INTEGER NOT NULL,
    value_json TEXT NOT NULL DEFAULT '{}',
    done INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (checkin_date, habit_id),
    FOREIGN KEY (checkin_date) REFERENCES checkins(date) ON DELETE CASCADE,
    FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
);

CREATE INDEX idx_habit_entries_habit ON habit_entries(habit_id);

CREATE TABLE trigger_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    text TEXT NOT NULL,
    tag TEXT
);

CREATE TABLE weekly_reviews (
    week_start_date TEXT PRIMARY KEY,
    notes_text TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
