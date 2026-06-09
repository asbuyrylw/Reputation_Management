-- Reputation Crowding-Out Engine -- schema additions (v7: competitor benchmarking)
-- Run after schema_v6.sql:  psql "$REP_DB_DSN" -f schema_v7.sql
-- Idempotent. Lets the engine measure, for a subject business, how often AI engines
-- surface IT versus named competitors across the same category prompts -- the
-- competitive share-of-voice view buyers expect.

CREATE TABLE IF NOT EXISTS competitors (
    id            BIGSERIAL PRIMARY KEY,
    business_id   BIGINT,                 -- the SUBJECT business this competitor is tracked for
    name          TEXT,
    domain        TEXT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE (business_id, name)
);
CREATE INDEX IF NOT EXISTS idx_competitors_biz ON competitors(business_id);

-- Per-competitor audit answers, mirroring the `answers` table but keyed to a
-- competitor instead of the subject business. Kept separate so competitor data
-- never contaminates the subject's own metrics/gap model.
CREATE TABLE IF NOT EXISTS competitor_answers (
    id              BIGSERIAL PRIMARY KEY,
    competitor_id   BIGINT REFERENCES competitors(id),
    business_id     BIGINT,               -- subject business (for convenient filtering)
    run_id          BIGINT,               -- a shared benchmark run id (groups subject+competitors)
    engine          TEXT,
    prompt          TEXT,
    answer_text     TEXT,
    cited_sources   JSONB DEFAULT '[]'::jsonb,
    mentions_subject  BOOLEAN,            -- did the answer mention the SUBJECT business?
    mentions_competitor BOOLEAN,          -- did it mention THIS competitor?
    sample_idx      INT DEFAULT 0,
    failed          BOOLEAN DEFAULT FALSE,
    persona         TEXT DEFAULT '',
    location        TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_compans_comp ON competitor_answers(competitor_id);
CREATE INDEX IF NOT EXISTS idx_compans_run ON competitor_answers(run_id);
