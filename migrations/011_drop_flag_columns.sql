-- Drop the three day-flag columns from checkins. They were never wired into
-- the score model and ship as visual noise on the check-in form.
ALTER TABLE checkins DROP COLUMN caffeine;
ALTER TABLE checkins DROP COLUMN alcohol;
ALTER TABLE checkins DROP COLUMN late_meal;
