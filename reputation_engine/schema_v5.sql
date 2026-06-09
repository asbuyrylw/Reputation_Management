-- Reputation Crowding-Out Engine -- schema additions (v5: citation/persona/location)
-- Run after schema_v4.sql:  psql "$REP_DB_DSN" -f schema_v5.sql
-- Idempotent. Implements the OpenCite-style metrics: which domains AI engines cite
-- for a business, how that shifts over time (momentum), and how answers differ by
-- asker persona and location.

-- Persona/location dimensions on each recorded answer. Default '' = the generic
-- (no-persona, no-location) probe, so existing rows remain valid.
ALTER TABLE answers ADD COLUMN IF NOT EXISTS persona TEXT DEFAULT '';
ALTER TABLE answers ADD COLUMN IF NOT EXISTS location TEXT DEFAULT '';

-- Citation momentum: per business + cited domain, tracked across runs. Lets us show
-- which sources AI engines lean on, whether they're rising/falling, and whether they
-- are owned/neutral/contested -- the share-of-voice view.
CREATE TABLE IF NOT EXISTS citation_momentum (
    id            BIGSERIAL PRIMARY KEY,
    business_id   BIGINT,
    domain        TEXT,
    run_id        BIGINT,
    cite_count    INT,            -- times this domain was cited in this run
    share         NUMERIC(6,4),   -- this domain's share of all citations in the run
    classification TEXT,          -- owned | neutral | contested | unknown
    first_seen_run BIGINT,
    last_seen_run  BIGINT,
    created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_citemom_biz ON citation_momentum(business_id, domain);
CREATE INDEX IF NOT EXISTS idx_citemom_run ON citation_momentum(run_id);
