-- Reputation Crowding-Out Engine -- consolidated schema
-- Modules also create their tables on first run (idempotent), but this file
-- lets you provision the database up front:  psql "$REP_DB_DSN" -f schema.sql

CREATE TABLE IF NOT EXISTS businesses (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    domain          TEXT,
    services        TEXT,
    profile         TEXT,
    goal            TEXT,
    contested_terms TEXT,            -- comma-separated terms to OUT-COMPETE (not suppress)
    geo             TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_runs (
    id           BIGSERIAL PRIMARY KEY,
    business_id  BIGINT REFERENCES businesses(id),
    started_at   TIMESTAMPTZ DEFAULT now(),
    finished_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS answers (
    id                 BIGSERIAL PRIMARY KEY,
    run_id             BIGINT REFERENCES audit_runs(id),
    business_id        BIGINT REFERENCES businesses(id),
    engine             TEXT,
    prompt             TEXT,
    answer_text        TEXT,
    cited_sources      JSONB DEFAULT '[]'::jsonb,
    sentiment          TEXT,
    goal_alignment     NUMERIC(4,2),
    mentions_contested BOOLEAN DEFAULT FALSE,
    surfaces_owned     BOOLEAN DEFAULT FALSE,
    raw                JSONB DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_answers_run ON answers(run_id);
CREATE INDEX IF NOT EXISTS idx_answers_biz ON answers(business_id);

CREATE TABLE IF NOT EXISTS gap_models (
    id           BIGSERIAL PRIMARY KEY,
    business_id  BIGINT REFERENCES businesses(id),
    run_id       BIGINT REFERENCES audit_runs(id),
    model        JSONB,
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS site_audits (
    id           BIGSERIAL PRIMARY KEY,
    business_id  BIGINT REFERENCES businesses(id),
    run_id       BIGINT REFERENCES audit_runs(id),
    summary      JSONB,
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS strategy_plans (
    id           BIGSERIAL PRIMARY KEY,
    business_id  BIGINT REFERENCES businesses(id),
    plan         JSONB,
    created_at   TIMESTAMPTZ DEFAULT now()
);
