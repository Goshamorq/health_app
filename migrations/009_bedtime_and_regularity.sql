ALTER TABLE checkins ADD COLUMN bedtime TEXT;

INSERT OR IGNORE INTO settings (key, value) VALUES
    ('sleep_bedtime_std_max_min', '30'),
    ('sleep_min_bedtime_samples', '4');
