-- Reputation Crowding-Out Engine -- schema additions (v8: mention monitoring + replies)
-- Run after schema_v7.sql:  psql "$REP_DB_DSN" -f schema_v8.sql
-- Idempotent. Monitors mentions of any business/keyword across pluggable sources and
-- drafts replies for HUMAN APPROVAL (never auto-posts). No per-business license cap --
-- monitor as many businesses and keywords as your own infrastructure allows.

-- Keywords/queries to monitor, per business. Unlimited rows.
CREATE TABLE IF NOT EXISTS monitor_keywords (
    id            BIGSERIAL PRIMARY KEY,
    business_id   BIGINT,
    keyword       TEXT,
    negative      BOOLEAN DEFAULT FALSE,     -- exclude matches containing this term
    active        BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE (business_id, keyword)
);
CREATE INDEX IF NOT EXISTS idx_monkw_biz ON monitor_keywords(business_id);

-- Discovered mentions. source is the adapter that found it (reddit, rss, web, etc).
CREATE TABLE IF NOT EXISTS mentions (
    id            BIGSERIAL PRIMARY KEY,
    business_id   BIGINT,
    source        TEXT,
    source_url    TEXT,
    external_id   TEXT,                       -- adapter's id for dedup
    author        TEXT,
    title         TEXT,
    body          TEXT,
    matched_keyword TEXT,
    sentiment     TEXT,                        -- positive | neutral | negative | NULL
    relevance     NUMERIC(4,3),                -- 0..1 heuristic relevance
    status        TEXT DEFAULT 'new',          -- new | drafted | ignored | actioned
    discovered_at TIMESTAMPTZ DEFAULT now(),
    dedup_hash    TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_mentions_biz ON mentions(business_id, status);

-- Drafted replies. ALWAYS pending_review; a human approves before anything is posted.
CREATE TABLE IF NOT EXISTS mention_replies (
    id              BIGSERIAL PRIMARY KEY,
    mention_id      BIGINT REFERENCES mentions(id),
    business_id     BIGINT,
    draft           TEXT,
    tone            TEXT,
    compliance_pass BOOLEAN,                   -- NULL = screener unavailable -> human must review
    compliance_flags JSONB DEFAULT '[]'::jsonb,
    status          TEXT DEFAULT 'pending_review',  -- pending_review | approved | rejected | posted
    reviewer        TEXT,
    reviewed_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mreplies_status ON mention_replies(business_id, status);
