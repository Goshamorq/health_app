-- Replace subjective water labels (low/mid/good) with liter ranges.
-- Mapping:
--   low  -> "<1"     (under a litre)
--   mid  -> "1-1.5"  (middling)
--   good -> "1.5-2"  ("good" wasn't max-aspirational; 2+ is the new top bucket)
UPDATE checkins SET water_bucket = '<1'    WHERE water_bucket = 'low';
UPDATE checkins SET water_bucket = '1-1.5' WHERE water_bucket = 'mid';
UPDATE checkins SET water_bucket = '1.5-2' WHERE water_bucket = 'good';
