-- Reputation Crowding-Out Engine -- schema additions (v6: resumable runs)
-- Run after schema_v5.sql:  psql "$REP_DB_DSN" -f schema_v6.sql
-- Idempotent. Records each pipeline step's status per logical run so a failed or
-- interrupted run can resume from where it stopped instead of re-spending budget.

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id            BIGSERIAL PRIMARY KEY,
    business_id   BIGINT,
    kind          TEXT,                 -- 'run' | 'cycle'
    status        TEXT DEFAULT 'in_progress',  -- in_progress | complete | failed
    started_at    TIMESTAMPTZ DEFAULT now(),
    finished_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_pruns_biz ON pipeline_runs(business_id, kind, status);

CREATE TABLE IF NOT EXISTS pipeline_steps (
    id            BIGSERIAL PRIMARY KEY,
    pipeline_run_id BIGINT REFERENCES pipeline_runs(id),
    step_key      TEXT,                 -- stable identifier e.g. 'audit','gap_model'
    status        TEXT DEFAULT 'pending',  -- pending | done | failed
    error         TEXT,
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    UNIQUE (pipeline_run_id, step_key)
);
CREATE INDEX IF NOT EXISTS idx_psteps_run ON pipeline_steps(pipeline_run_id);
