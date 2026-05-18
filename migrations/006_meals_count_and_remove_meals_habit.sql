ALTER TABLE checkins ADD COLUMN meals_count INTEGER;

DELETE FROM habits WHERE name = '3 proper meals' AND pillar = 'food';
