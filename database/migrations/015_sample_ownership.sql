-- Migration: Per-user ownership of samples
-- Date: 2026-10-06
-- Description: Every sample belongs to the user who submitted it, and only that
-- user may see the sample and everything derived from it (pipeline runs, results,
-- AMR genes, taxonomy). Ownership lives on samples only; pipeline_runs and the
-- result tables inherit it through sample_id.
--
-- All samples that existed before this migration were submitted by the platform
-- operator account (nicolaedrabcinski) and are assigned to it. The same account
-- is the column default, so batch scripts that insert into samples directly
-- (scripts/batch, scripts/data_processors) keep attributing their samples to the
-- operator. The web API always sets owner_id explicitly.
-- Idempotent: safe to run more than once.

BEGIN;

DO $$
DECLARE
    operator_id INTEGER;
BEGIN
    SELECT user_id INTO operator_id FROM users WHERE username = 'nicolaedrabcinski';
    IF operator_id IS NULL THEN
        RAISE EXCEPTION 'Operator account nicolaedrabcinski not found';
    END IF;

    ALTER TABLE samples ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES users(user_id);

    UPDATE samples SET owner_id = operator_id WHERE owner_id IS NULL;

    EXECUTE format('ALTER TABLE samples ALTER COLUMN owner_id SET DEFAULT %s', operator_id);
    ALTER TABLE samples ALTER COLUMN owner_id SET NOT NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_samples_owner_id ON samples(owner_id);

COMMENT ON COLUMN samples.owner_id IS
    'User who submitted the sample; only this user can access it and its pipeline runs/results';

COMMIT;

SELECT u.username, COUNT(s.sample_id) AS samples
FROM users u
LEFT JOIN samples s ON s.owner_id = u.user_id
GROUP BY u.username
ORDER BY u.username;
