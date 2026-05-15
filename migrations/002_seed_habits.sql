INSERT INTO habits (pillar, name, type, threshold_config) VALUES
    ('sleep', 'In bed by 23:30',         'time',   '{"target":"23:30","direction":"before"}'),
    ('sleep', 'No screens after 22:00',  'time',   '{"target":"22:00","direction":"before"}'),
    ('sport', 'Movement 30+ min',        'binary', '{}'),
    ('sport', 'Stretching / mobility',   'binary', '{}'),
    ('food',  '3 proper meals',          'binary', '{}'),
    ('food',  'Veggies at lunch & dinner','binary', '{}');
