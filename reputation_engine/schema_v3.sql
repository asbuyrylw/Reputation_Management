-- Reputation Crowding-Out Engine -- schema additions (v3: content generation)
-- Run after schema_v2.sql:  psql "$REP_DB_DSN" -f schema_v3.sql
-- Idempotent.

-- ---------------------------------------------------------------------------
-- GENERATED CONTENT DRAFTS
-- Output of Module 6. AI generates -> self-eval scores -> compliance screen ->
-- queued for HUMAN review. Nothing here is auto-published. On approval, a human
-- (or the tracking module) promotes an approved draft into the `assets` table.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS content_drafts (
    id              BIGSERIAL PRIMARY KEY,
    business_id     BIGINT REFERENCES businesses(id),
    work_order_id   BIGINT,                 -- the gap/work order this fills
    asset_type      TEXT,                   -- owned_page | faq | schema | article | bio | gbp_post | review_request
    title           TEXT,
    body            TEXT,                   -- the generated draft (markdown / JSON-LD / copy)
    target_query    TEXT,                   -- the weak AI query this is meant to answer
    quality_score   NUMERIC(4,2),           -- self-eval 0..1
    quality_notes   JSONB DEFAULT '{}'::jsonb,
    revision_count  INT DEFAULT 0,          -- how many auto-revision passes were applied
    compliance_pass BOOLEAN,                -- did it clear the compliance screen
    compliance_flags JSONB DEFAULT '[]'::jsonb,
    status          TEXT DEFAULT 'pending_review',  -- pending_review|approved|rejected|published|needs_fix
    reviewer        TEXT,
    reviewed_at     TIMESTAMPTZ,
    published_asset_id BIGINT,              -- set when approved+promoted into assets
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_drafts_biz ON content_drafts(business_id);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON content_drafts(status);
