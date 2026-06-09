-- Reputation Crowding-Out Engine -- schema additions (v4: outcome feedback loop)
-- Run after schema_v3.sql:  psql "$REP_DB_DSN" -f schema_v4.sql
-- Idempotent.

-- ---------------------------------------------------------------------------
-- LEARNED EFFECTIVENESS
-- The outcome feedback loop (Module 9) measures, per business, how much each
-- asset/lever TYPE actually moved goal_alignment in the windows it was shipped.
-- These learned signals then recalibrate the timeline estimator and the
-- acceleration advisor away from generic literature defaults toward what has
-- actually worked for THIS business. Recomputed each cycle (idempotent upsert).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS learned_effectiveness (
    business_id     BIGINT,
    lever_type      TEXT,          -- asset_type / capability family (e.g. article, earned_link, review)
    obs_windows     INT,           -- how many run-windows contributed
    obs_units       INT,           -- total units of this type observed shipped
    gain_per_unit   NUMERIC(8,5),  -- learned monthly goal_alignment gain per unit
    confidence      TEXT,          -- low | medium | high (by sample size)
    updated_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (business_id, lever_type)
);

-- A per-business learned baseline monthly gain (overall trajectory), so the
-- estimator can prefer measured reality over BASE_MONTHLY_GAIN once it exists.
CREATE TABLE IF NOT EXISTS learned_baseline (
    business_id        BIGINT PRIMARY KEY,
    monthly_gain       NUMERIC(8,5),
    obs_windows        INT,
    confidence         TEXT,
    updated_at         TIMESTAMPTZ DEFAULT now()
);
