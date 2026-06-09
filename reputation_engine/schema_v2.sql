-- Reputation Crowding-Out Engine -- schema additions (v2: execution + attribution)
-- Run after schema.sql:  psql "$REP_DB_DSN" -f schema_v2.sql
-- All idempotent.

-- ---------------------------------------------------------------------------
-- WORK ORDER EXECUTION TRACKING
-- The system of record that turns "a plan" into "a running retainer program".
-- Each work order from a strategy_plan becomes a tracked, status-bearing row.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS work_orders (
    id              BIGSERIAL PRIMARY KEY,
    business_id     BIGINT REFERENCES businesses(id),
    plan_id         BIGINT REFERENCES strategy_plans(id),
    wo_code         TEXT,            -- e.g. WO-001 (from the generated plan)
    title           TEXT,
    capability      TEXT,
    execution       TEXT,            -- auto | semi | manual
    recommended_tool TEXT,
    instruction     TEXT,
    phase           TEXT,
    target_date     DATE,
    status          TEXT DEFAULT 'pending',   -- pending|in_progress|done|verified|skipped|blocked
    assignee        TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    verified_at     TIMESTAMPTZ,
    result_notes    TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_wo_biz ON work_orders(business_id);
CREATE INDEX IF NOT EXISTS idx_wo_status ON work_orders(status);

-- ---------------------------------------------------------------------------
-- PUBLISHED ASSETS / CORROBORATION EVENTS
-- The record of what actually went live and when -- the input to attribution.
-- A completed work order can produce one or more of these.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS assets (
    id              BIGSERIAL PRIMARY KEY,
    business_id     BIGINT REFERENCES businesses(id),
    work_order_id   BIGINT REFERENCES work_orders(id),
    asset_type      TEXT,            -- owned_page|schema|review_batch|press|podcast|partner|social|video
    title           TEXT,
    url             TEXT,
    surface         TEXT,            -- own_site|google_business|linkedin|reddit|press|podcast|youtube|x|facebook
    published_at    TIMESTAMPTZ DEFAULT now(),
    meta            JSONB DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_assets_biz ON assets(business_id);
CREATE INDEX IF NOT EXISTS idx_assets_pub ON assets(published_at);

-- ---------------------------------------------------------------------------
-- COST LEDGER
-- Per-call cost tracking so you know your COGS per audit and per client.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cost_ledger (
    id              BIGSERIAL PRIMARY KEY,
    business_id     BIGINT REFERENCES businesses(id),
    run_id          BIGINT,
    provider        TEXT,            -- anthropic|openai|perplexity|gemini
    operation       TEXT,            -- answer|score|gap|content
    model           TEXT,
    input_tokens    INT,
    output_tokens   INT,
    est_cost_usd    NUMERIC(10,5),
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cost_biz ON cost_ledger(business_id);
CREATE INDEX IF NOT EXISTS idx_cost_run ON cost_ledger(run_id);

-- ---------------------------------------------------------------------------
-- ATTRIBUTION SNAPSHOTS
-- Links metric movement between two runs to the assets published in the
-- interval, so the report can say "these actions preceded this improvement."
-- Correlational, clearly labeled as such -- not a causal claim.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attribution (
    id              BIGSERIAL PRIMARY KEY,
    business_id     BIGINT REFERENCES businesses(id),
    from_run_id     BIGINT,
    to_run_id       BIGINT,
    metric          TEXT,            -- goal_alignment|contested_rate|owned_rate|share_of_voice
    delta           NUMERIC(8,4),
    assets_in_window JSONB,          -- asset ids + summaries published between the runs
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_attr_biz ON attribution(business_id);

-- ---------------------------------------------------------------------------
-- Multi-sample support: answers already store per-call rows; we add a sample
-- index so repeated runs of the same prompt in one audit can be averaged.
-- ---------------------------------------------------------------------------
ALTER TABLE answers ADD COLUMN IF NOT EXISTS sample_idx INT DEFAULT 0;
ALTER TABLE answers ADD COLUMN IF NOT EXISTS failed BOOLEAN DEFAULT FALSE;

-- ---------------------------------------------------------------------------
-- Per-business config (replaces global tool flags / goals as constants)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS business_config (
    business_id     BIGINT PRIMARY KEY REFERENCES businesses(id),
    disabled_tools  JSONB DEFAULT '[]'::jsonb,   -- tool keys this client can't/won't use
    samples_per_prompt INT DEFAULT 2,
    monthly_budget_usd NUMERIC(10,2) DEFAULT 50.0,
    alert_threshold NUMERIC(4,2) DEFAULT 0.15,   -- contested-rate jump that triggers an alert
    updated_at      TIMESTAMPTZ DEFAULT now()
);
