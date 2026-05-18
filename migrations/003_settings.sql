CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO settings (key, value) VALUES
    ('streak_forgiveness_enabled', '1'),
    ('streak_forgiveness_threshold', '1');
