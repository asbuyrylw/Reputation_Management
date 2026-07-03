# rep_engine Integrations, Publishing & Response-Approval System â€” Consolidated Design (FINAL)

**Status:** Design of record. Merges five module designs (Connections Vault, Publishing Adapters, GBP Reviews, Unified Approval Queue, Console UI, Migrations) into one coherent spec, with every critic finding integrated in place. Lead-architect resolutions are called out inline in **`Resolved:`** notes; review-driven corrections are marked **`[review-fix]`**.

Verified against the actual code: `api/jobs.py` (`uq_api_jobs_active(business_id, job_type)` dedup, `rate_ok` keyed `job:{business_id}:{job_type}`), `content_generator.py` (`approve()` blocks only `pass IS False`; `update_draft` re-runs deterministic-only and can only set `pass=False|None`; `_COMPLIANCE_RULES` are 4 financial regexes; `COMPLIANCE_SYSTEM` "non-financial â†’ pass it"), `mention_monitor.py` (`_ensure()` is CREATE-TABLE-only; `approve()/reject()` are id-only, set `approved/rejected`, mentionsâ†’`actioned`), `notifications.check_and_notify` (fixed `created` dict; `neg_mentions` LIMIT 25; `drafts_waiting` counts only `content_drafts`), `scheduler.py` (top-level `rep_engine/scheduler.py`; `tick()` reads the `schedules` table, `DEFAULT_CADENCES` is a hint only), `api/main.py` (explicit `include_router` block; double-submit CSRF on cookie+non-bearer mutating methods, GET exempt), `deps.py` (`require_super_admin`, `require_org_manager`, `require_business_editor`, `authorize_business`), `netguard.assert_url_allowed`, `http.request_json(..., guard_redirects=True)`, `gdpr.py` (auto-discovered scoped delete/export).

---

## 0. Contradictions resolved (read first)

| # | Conflict | Modules in disagreement | **Resolution (canonical)** |
|---|---|---|---|
| R1 | Connections table name | `platform_connections` vs `oauth_connections` | **`platform_connections`** everywhere. |
| R2 | Encryption env key | `CONNECTIONS_ENC_KEY` vs `TOKEN_ENC_KEY` | **`TOKEN_ENC_KEY`**. One key, asserted `!= JWT_SECRET` at startup. `rep_engine/crypto.py` reads it. |
| R3 | Credential column shape | one `credential_enc` blob vs split tokens | **Split columns** (`access_token_enc`, `refresh_token_enc`) **plus** `meta` JSONB for non-secret extras (site_url, wp_user, site_timezone). App-password/profile-key secrets go in `access_token_enc`, `token_type` discriminates. |
| R4 | Migration numbering | every module claimed `0040` | **Five-file chain `0040`â†’`0044`**. Verified head is `0039_super_admin_billing_flags`; `0040` is next free. |
| R5 | Per-tenant automation settings | `automation_settings` vs `integration_settings` vs `businesses` columns | **`integration_settings`** (0044), carrying all guardrail fields. One row per business; **auto-created at onboarding, default OFF**, and every reader COALESCEs to safe defaults if absent. |

Preserved judgment calls:
- **GBP `reviews`/`review_replies` are dedicated tables** (0042), not folded into `mention_replies`. The unified queue *reads* both shapes and normalizes them into one `QueueItem`, **cross-deduping by `(source, external_id)`** so one Google review never appears as both a `reviews` row and a Serper-sourced `mentions` row (Â§5.3, Â§6.1).
- **0043 downgrade is intentionally asymmetric** (drops only added columns/constraints, never the three pre-existing `_ensure()` tables).

### Critical review-driven corrections (the design changed because of these â€” see Â§11 for the full ledger)

- **`[review-fix] No per-item jobs.`** The job seam dedups on `(business_id, job_type)`, so per-item `publish(target_id)` / `post_review_reply(reply_id)` jobs would silently strand all but the first. **All posting is done by singleton *drain* jobs** (`publish_sweep`, `post_review_replies`, `post_mention_replies`) that claim and process **every** due row for the business in one invocation. Exactly-once lives on the content row's status claim, not on `api_jobs`. (Â§3.3, Â§4.4, Â§6.2)
- **`[review-fix] FTC checks are real code, not prose.`** New deterministic reply-screen rules (first-person-customer voice, review solicitation/incentive, impersonation) are added to `content_generator` and **run on every reply path**. The LLM screen is extended so replies are not auto-passed as "non-financial." Until these land, **all reply paths are forced `manual`.** (Â§0.inv5, Â§3.2, Â§5.6)
- **`[review-fix] SSRF guard on every outbound call.`** WordPress publish/verify, Ayrshare, GBP ingest/reply, and OAuth token endpoints all go through `http.request_json(..., guard_redirects=True)` / `netguard.assert_url_allowed(url)` with a provider-host allowlist. No raw `requests.*` to a tenant-supplied URL. (Â§4.3, Â§7, inv #9)
- **`[review-fix] Status vocabularies reconciled with existing readers.`** New mention statuses extend the existing `approved/rejected/actioned` set; `list_pending`, `check_and_notify`, and the console are updated in lock-step. (Â§5.4)
- **`[review-fix] Compliance is enforced at target-creation, copied onto the asset.`** `assets` gains a `compliance_pass` column; the runner re-checks `compliance_pass IS TRUE` before any auto-post. (Â§2.2, Â§4.5)
- **`[review-fix] Connection-health is part of the claim.`** Runner claims join `platform_connections.status='active'`; revoke/disconnect transitions dependent queued/scheduled rows to `needs_reconnect`. Runtime 401/`invalid_grant` immediately marks the connection and surfaces "Reconnect to post." (Â§4.4, Â§6, Â§7.4â€“7.5)
- **`[review-fix] Network-grain fan-out.`** One `publish_targets` row **per network** is created up front; there is no NULL-network parent that re-drives already-live networks on retry. (Â§2.2, Â§4.3, Â§4.4)
- **`[review-fix] GDPR/retention.`** A reconcile/erasure job redacts third-party author PII and soft-deletes `mentions`/`reviews` whose source content disappeared. (Â§2.2, Â§5.7)
- **`[review-fix] Owner-tier gate + global kill switch.`** Enabling auto-post (`allow_owned_autopost`, `auto_reply_*`, raising caps, `auto_platforms`) requires `require_org_manager`; a platform-wide `AUTOPOST_GLOBAL_ENABLED` env flag (default off) is checked in the runner. (Â§3.4, Â§5.2, Â§8.2)
- **`[review-fix] scheduler path + recurrence.`** It is `rep_engine/scheduler.py` (not `api/`); recurring jobs require `schedules` rows via `upsert_schedule` (created at connection/onboarding time). `DEFAULT_CADENCES` edits are cosmetic. (Â§3.2)
- **`[review-fix] Routers are registered.`** All four routers are added to `create_app().include_router(...)`; the unprefixed OAuth callback intentionally bypasses `authorize_business` (tenancy from `oauth_states`) and is CSRF-safe as a GET. (Â§3.4)

---

## 1. Overview & Principles

This turns the engine from "monitor + draft, human posts by hand" into "monitor + draft + **publish/reply through owned channels**, still human-gated," by **extending** existing seams:

- **Module 13 (`mention_monitor.py`)** keeps `discover() â†’ draft_replies() â†’ list_pending/approve/reject` and its `monitor_keywords`/`mentions`/`mention_replies` tables. We add columns (surface, connection, auto-policy), branch `approve()` on surface, and **re-scope every reader/writer by `business_id`**.
- **The `assets` publish surface** (`published_url`/`published_status`/`summary`, manual today) becomes the **write-back target** of an automated publisher. Manual `PATCH /assets/{id}` stays as an escape hatch.
- **`social_presence`** stays the presence tracker; `platform_connections` is the new *credential* layer beneath it.

### Non-negotiable invariants (enforced structurally)

1. **Nothing is auto-posted to a third-party surface â€” ever.** Reddit, X threads, forums, Yelp, RipoffReport, Glassdoor, BBB, Trustpilot, news: **draft + alert only**, no code path posts to them.
2. **The only auto-post path** is `owned` surface + tenant opted in (`require_org_manager` to enable) + `compliance_pass IS True` (strictly) + within guardrails + `AUTOPOST_GLOBAL_ENABLED`. This is GBP review replies and owned blog/page posts only.
3. **Compliance fails safe.** `_compliance()` returns `True | False | None`. `False` or `None` â‡’ forced manual. **Editing a draft/reply re-runs the *deterministic* (non-injectable) screen in-request and resets `compliance_pass` to `False` (hard-rule hit) or `None` (unscreened) â€” never `True`.** A full LLM re-screen happens only in a job, so a freshly edited reply can never be auto-eligible until re-screened. (Matches `content_generator.update_draft`.)
4. **LLM/network spend never happens in an HTTP request.** Drafting and all outbound third-party writes run inside budget/rate-gated **jobs**. The cheap, synchronous OAuth *token exchange* is the only network call allowed in a request (mirrors the Stripe webhook), because it is bound to the user's click and spends nothing â€” and it **also goes through `netguard`**.
5. **FTC fake-reviews rule (16 CFR Part 465):** the system only drafts **brand replies to genuine items**; it has **no path** that creates or solicits reviews. **Deterministic, in-code checks** flag first-person-customer voice, review solicitation/incentive, and impersonation on every reply, and the LLM screen no longer auto-passes replies as "non-financial." Until these checks ship, every reply path is `manual`.
6. **Reddit/Yelp guardrail:** always third-party regardless of any connection/opt-in. `integration_settings.blocked_channels` defaults `["reddit","yelp"]`; `route()` forces `manual`; the publish registry omits them entirely. Optional per-platform engagement caps + an explicit "you are responsible for the platform's ToS" notice on the Copy-draft affordance.
7. **Secrets at rest:** OAuth tokens / app-passwords / profile-keys are **Fernet ciphertext** in `access_token_enc`/`refresh_token_enc`. Key in env (`TOKEN_ENC_KEY`, asserted `!= JWT_SECRET`), never in Postgres. `crypto.py` is the only reversible-crypto seam; **`vault.py` is the only importer** (CI grep-asserted). Plaintext never crosses a `log.*` call; every `*_error`/`*_summary`/`external_ack` field is run through `_redact()` before persist.
8. **Idempotency + tenant isolation:** every publish/reply is exactly-once per network via the content-row status claim; **every business-prefixed handler AND every post job re-passes `business_id` into the SQL `WHERE`** (post jobs additionally verify `connection.business_id == business_id` before decrypt); the OAuth callback is scoped solely by an HMAC-signed, single-use, TTL'd `oauth_states` row.
9. **`[review-fix]` SSRF defense:** all outbound provider HTTP goes through `http.request_json(..., guard_redirects=True)` or `netguard.assert_url_allowed(url)` immediately before the call, with a host allowlist for fixed provider APIs (`api.ayrshare.com`, `oauth2.googleapis.com`, `mybusiness.googleapis.com`, `accounts.google.com`). Tenant-supplied hosts (WordPress `site_url`) are https-only and IP-validated on every redirect hop.

---

## 2. Data Model

### 2.1 ER summary

```
businesses â”€â”¬â”€< platform_connections          (per-tenant credential vault; Fernet at rest)
            â”‚       â”‚  ON DELETE CASCADE
            â”‚       â”œâ”€â”€< publish_targets        (ON DELETE SET NULL; revoke â†’ rows go 'needs_reconnect')
            â”‚       â”œâ”€â”€< reviews                (ON DELETE SET NULL)
            â”‚       â”œâ”€â”€< review_replies         (ON DELETE SET NULL)
            â”‚       â””â”€â”€< mentions / mention_replies.target_connection_id (ON DELETE SET NULL)
            â”‚
            â”œâ”€< assets â”€â”€< publish_targets â”€â”€< publish_attempts   (asset â†’ per-network channels â†’ per-try audit)
            â”‚       (publish job writes published_url/published_status='live' back; assets carries compliance_pass)
            â”œâ”€< work_orders  â”€â”€ publish_targets.work_order_id
            â”œâ”€< mentions â”€â”€< mention_replies     (Module 13, extended; business-scoped readers)
            â”œâ”€< reviews â”€â”€< review_replies       (GBP ingest + reply queue)
            â”œâ”€< monitor_keywords
            â””â”€â”€â”€ integration_settings            (1 row/business, auto-created OFF; readers COALESCE)

oauth_states  (short-lived OAuth handshake; stateâ†’business_id+platform; deleted on callback)
```

### 2.2 Consolidated DDL

Authoritative DDL is the five migration files in Â§9; the views below are byte-compatible.

**`platform_connections`** (0040):
```sql
CREATE TABLE IF NOT EXISTS platform_connections (
    id BIGSERIAL PRIMARY KEY,
    business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,                 -- wordpress_org|wordpress_com|ayrshare|google_business_profile|meta|linkedin|x|yelp_read
    label TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending|active|error|revoked|expired
    access_token_enc TEXT,              -- Fernet ciphertext; OAuth access token OR the single app-pw/profile-key secret
    refresh_token_enc TEXT,
    token_type TEXT,                    -- bearer|basic|app_password|ayrshare_profile|google_oauth
    expires_at TIMESTAMPTZ,
    account_ref TEXT,                   -- GBP accountId / WP site id / FB page id / Ayrshare owner
    profile_ref TEXT,                   -- GBP locationId / Ayrshare profileKey / IG business id
    external_id TEXT,
    scopes JSONB DEFAULT '[]'::jsonb,
    gbp_access TEXT,                    -- NULL|pending|approved  (GBP allowlist state; UI/auto gate)
    meta JSONB DEFAULT '{}'::jsonb,     -- site_url, wp_user, api_host, site_timezone, version pins (non-secret)
    last_error TEXT,                    -- REDACTED
    last_used_at TIMESTAMPTZ,
    connected_by BIGINT REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (business_id, kind, account_ref)
);
-- idx_platform_connections_business, _kind, partial _expiry (refresh sweep), partial _active (runner join)
```

**`oauth_states`** (0040 â€” same migration, connections layer):
```sql
CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,             -- secrets.token_urlsafe(>=128 bits), HMAC-signed (domain-separated)
    business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    redirect_uri TEXT,                  -- stored for record only; NEVER reflected into the Location header
    created_by BIGINT REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL    -- ~10 min TTL; row DELETE...RETURNING on callback (single-use)
);
```

**`publish_targets`** + **`publish_attempts`** (0041) â€” **network-grain** fan-out + per-try audit:
```sql
CREATE TABLE IF NOT EXISTS publish_targets (
    id BIGSERIAL PRIMARY KEY,
    business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    asset_id BIGINT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    connection_id BIGINT REFERENCES platform_connections(id) ON DELETE SET NULL,
    work_order_id BIGINT,
    channel TEXT NOT NULL,              -- wordpress|facebook|instagram|linkedin|x|pinterest|gbp_post (NOT reddit/yelp)
    network TEXT NOT NULL DEFAULT '_',  -- per-network grain; '_' for single-target (WP/GBP). NEVER NULL parent.
    payload_kind TEXT NOT NULL DEFAULT 'article',  -- article|social|link
    status TEXT NOT NULL DEFAULT 'queued',
        -- queued|publishing|live|scheduled|failed|skipped|canceled|needs_reconnect
    routing JSONB DEFAULT '{}'::jsonb,
    scheduled_for TIMESTAMPTZ,
    external_id TEXT, external_url TEXT, published_at TIMESTAMPTZ,
    idempotency_key TEXT NOT NULL,      -- f"{asset_id}:{connection_id}:{network}"  (network ALWAYS present)
    attempts INT NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    last_error TEXT,                    -- REDACTED
    job_id BIGINT REFERENCES api_jobs(id) ON DELETE SET NULL,
    created_by BIGINT REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (asset_id, channel, connection_id, network)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_publish_targets_idem ON publish_targets (idempotency_key);
CREATE INDEX IF NOT EXISTS idx_publish_targets_due
    ON publish_targets (status) WHERE status IN ('queued','failed','scheduled');

CREATE TABLE IF NOT EXISTS publish_attempts (
    id BIGSERIAL PRIMARY KEY,
    target_id BIGINT NOT NULL REFERENCES publish_targets(id) ON DELETE CASCADE,
    business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    job_id BIGINT REFERENCES api_jobs(id) ON DELETE SET NULL,
    attempt_no INT, ok BOOLEAN NOT NULL, http_status INT,
    external_id TEXT, external_url TEXT,
    request_summary JSONB DEFAULT '{}'::jsonb,   -- REDACTED; never tokens/headers
    response_summary JSONB DEFAULT '{}'::jsonb,  -- REDACTED
    error TEXT,                                  -- REDACTED
    retryable BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);
```
> **`[review-fix]`** fan-out idempotency is at the network grain: one row per network up front (`network` never NULL), so a retry of one network can never re-drive an already-live sibling. The `UNIQUE(asset_id,channel,connection_id,network)` plus the idempotency index enforce exactly-once.

**`reviews`** + **`review_replies`** (0042):
```sql
CREATE TABLE IF NOT EXISTS reviews (
    id BIGSERIAL PRIMARY KEY,
    business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    connection_id BIGINT REFERENCES platform_connections(id) ON DELETE SET NULL,
    source TEXT NOT NULL,               -- google_business_profile|yelp|facebook (only GBP replyable)
    external_id TEXT,                   -- GBP reviewId
    location_ref TEXT,
    author TEXT, rating NUMERIC(2,1),
    title TEXT, body TEXT, review_url TEXT,
    sentiment TEXT,                     -- positive|neutral|negative (from rating)
    status TEXT NOT NULL DEFAULT 'new', -- new|drafted|replied|ignored|gone
    reviewed_at TIMESTAMPTZ, review_updated_at TIMESTAMPTZ,   -- vendor updateTime (edited-review detection)
    author_pii_redacted BOOLEAN NOT NULL DEFAULT FALSE,      -- GDPR: author redacted after draft
    last_seen_at TIMESTAMPTZ DEFAULT now(),                   -- reconcile: source still present
    discovered_at TIMESTAMPTZ DEFAULT now(),
    meta JSONB DEFAULT '{}'::jsonb,
    dedup_hash TEXT UNIQUE              -- source+external_id; idempotent ingest
);

CREATE TABLE IF NOT EXISTS review_replies (
    id BIGSERIAL PRIMARY KEY,
    review_id BIGINT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    connection_id BIGINT REFERENCES platform_connections(id) ON DELETE SET NULL,
    draft TEXT, tone TEXT,
    compliance_pass BOOLEAN, compliance_flags JSONB DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending_review',
        -- pending_review|approved|auto_posted_pending|posting|posted|auto_posted|rejected|failed|superseded
    auto_generated BOOLEAN NOT NULL DEFAULT TRUE,
    reviewer TEXT,                      -- human-readable approver name (existing convention) or 'auto'
    reviewed_at TIMESTAMPTZ, posted_at TIMESTAMPTZ,
    external_url TEXT, external_ack JSONB,   -- REDACTED raw GBP updateReply response = proof-of-post
    edits JSONB DEFAULT '[]'::jsonb,    -- append {at,by,prev_text} per edit (FTC edit trail)
    last_error TEXT,                    -- REDACTED
    job_id BIGINT REFERENCES api_jobs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
-- uq_review_replies_active: partial unique (review_id) WHERE status NOT IN ('rejected','failed','superseded')
```

**`assets` addition** (0041, with `publish_targets`):
```sql
ALTER TABLE assets ADD COLUMN IF NOT EXISTS compliance_pass BOOLEAN;  -- copied from the source draft at approve()
```
> **`[review-fix]`** the runner re-checks `assets.compliance_pass IS TRUE` before any auto-post. `approve()` (which has the draft's verdict) sets it; manual `PATCH` assets are `published_status='live'` directly by a human and never auto-published.

**`mentions` / `mention_replies` additions** (0043):
- `mentions`: `surface TEXT DEFAULT 'third_party'`, `target_connection_id BIGINT REFERENCES platform_connections(id) ON DELETE SET NULL`, `external_url TEXT`, `external_id TEXT` (already exists), `author_pii_redacted BOOLEAN DEFAULT FALSE`, `last_seen_at TIMESTAMPTZ DEFAULT now()`.
- `mention_replies`: `surface TEXT DEFAULT 'third_party'`, `target_connection_id BIGINT`, `auto_policy TEXT DEFAULT 'manual'` (`manual|auto_eligible`), `posted_at`, `external_url`, `external_post_id`, `posted_by TEXT`, `last_error TEXT` (REDACTED), `job_id BIGINT`.
> **Resolved:** `auto_policy` value set is `manual|auto_eligible` (matches `route()` output). Defaults are the safe values so legacy rows can never auto-post. **`[review-fix]` `mention_monitor._ensure()` is updated to run the same `ADD COLUMN IF NOT EXISTS` set** so a fresh test DB matches alembic-migrated prod; a parity test asserts the `_ensure()` column set equals the 0043 set.

**`integration_settings`** (0044) â€” one row/business, **auto-created OFF at onboarding**, readers COALESCE:
```sql
CREATE TABLE IF NOT EXISTS integration_settings (
    business_id BIGINT PRIMARY KEY REFERENCES businesses(id) ON DELETE CASCADE,
    business_timezone TEXT NOT NULL DEFAULT 'UTC',     -- source of truth for quiet_hours + cap windows
    require_approval BOOLEAN NOT NULL DEFAULT TRUE,
    allow_owned_autopost BOOLEAN NOT NULL DEFAULT FALSE,
    auto_reply_reviews BOOLEAN NOT NULL DEFAULT FALSE,
    auto_reply_mentions BOOLEAN NOT NULL DEFAULT FALSE, -- exists but third_party route ignores it
    review_rating_threshold INT NOT NULL DEFAULT 3,
    auto_reply_min_stars SMALLINT NOT NULL DEFAULT 4,
    auto_reply_max_len INT NOT NULL DEFAULT 600,
    auto_platforms JSONB DEFAULT '[]'::jsonb,
    never_auto_sentiments JSONB DEFAULT '["negative"]'::jsonb,
    daily_autopost_cap INT NOT NULL DEFAULT 10,
    hourly_auto_cap INT NOT NULL DEFAULT 3,
    warmup_manual_count INT NOT NULL DEFAULT 20,
    quiet_hours JSONB DEFAULT '{}'::jsonb,             -- {start,end} evaluated in business_timezone
    banned_phrases JSONB DEFAULT '[]'::jsonb,
    allowed_channels JSONB DEFAULT '[]'::jsonb,
    blocked_channels JSONB DEFAULT '["reddit","yelp"]'::jsonb,
    third_party_weekly_draft_cap INT NOT NULL DEFAULT 0,  -- 0=unlimited; >0 throttles per-platform draft surfacing
    disclosure_text TEXT,
    notify_email BOOLEAN NOT NULL DEFAULT TRUE,
    notify_on_auto BOOLEAN NOT NULL DEFAULT TRUE,
    third_party_engage_default TEXT NOT NULL DEFAULT 'draft_alert',
    updated_by BIGINT REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now()
);
```
> **`[review-fix]`** a missing row = all-safe-off: `_settings(business_id)` returns a dataclass with these defaults if no row exists, so `route()`/`guardrails_ok()` never crash on cold start. Onboarding inserts the OFF row.

---

## 3. Module / Folder Layout

### 3.1 New backend packages

```
rep_engine/
  crypto.py                    # NEW. Fernet/MultiFernet at-rest crypto (key=TOKEN_ENC_KEY). Only reversible-crypto seam.
  response_policy.py           # NEW. classify_surface(), route(), guardrails_ok(), list_queue(), _settings() (COALESCE).
  gbp_reviews.py               # NEW. ingest(), _draft_pending(), post_reply(), reconcile() (re-scrape/erasure).
  reply_compliance.py          # NEW. deterministic FTC reply screen (first-person voice, solicitation, impersonation).

  connections/                 # NEW package
    vault.py                   # CRUD over platform_connections; ONLY importer of crypto; access_token(conn_id);
                               #   upsert_connection(); refresh_due(); mark_status(); test_connection(); _redact().
    oauth.py                   # build_state()/verify_state() (token_urlsafe + domain-separated HMAC); exchange/refresh.
    providers/{wordpress,ayrshare,google}.py   # all I/O via http.request_json(guard_redirects=True)
    status.py                  # test_connection(): provider liveness probe -> active|expired|revoked|error
  publishing/
    base.py registry.py wordpress.py ayrshare.py google_business.py runner.py   # runner = only DB-touching piece
```

### 3.2 Existing files that change

| File | Change |
|---|---|
| `rep_engine/mention_monitor.py` | **`_ensure()` gains the 0043 `ADD COLUMN IF NOT EXISTS` set** (fresh-DB parity). `discover()` calls `response_policy.classify_surface()`, writes `surface`/`target_connection_id`/`external_url`, and **skips `source='reviews'` for a GBP-connected location** (gbp_reviews owns it; cross-dedup by `(source,external_id)`). `draft_replies()` calls `route()`. `approve()`/`reject()` **re-scoped to `WHERE id=%s AND business_id=%s`**, branch on `surface` (ownedâ†’set `approved`, enqueue the `post_mention_replies` drain; third_partyâ†’`approved` sub-state `handled`/`rejected`). New statuses extend the existing set: `approved` (+ `posted`/`handled` sub-states), `rejected`, `actioned`. `list_pending` unchanged (still filters `pending_review`). |
| `rep_engine/content_generator.py` | Add shared `draft_reply(system, payload, *, max_tokens, fallback)` (one fenced-LLM drafter for mentions+reviews). **Extend `COMPLIANCE_SYSTEM`** so review/mention replies are screened (not auto-passed as non-financial). `approve()` **copies the draft's `compliance_pass` onto the new asset row.** Edit path keeps existing deterministic-only re-screen semantics (inv #3). |
| `rep_engine/reply_compliance.py` | **NEW deterministic checks** run inside `_compliance` for reply payloads: first-person-customer voice (`\bas a customer\b`, leading "I bought/used/visited", first-person without brand framing), solicitation/incentive (`leave (us )?a review`, `in exchange for`, `discount for a review`), impersonation. A hit is authoritative â†’ `pass=False`. |
| `rep_engine/api/jobs.py` | Register **drain** job types (not per-item) in `JOB_DISPATCH` + `_JOB_RATE_LIMITS` (Â§3.3). None in `billing.AUDIT_JOB_TYPES`. Lazy `_imp(...)`. |
| `rep_engine/scheduler.py` *(top-level, not api/)* | `DEFAULT_CADENCES` hint additions are cosmetic. **Real recurrence requires `schedules` rows via `upsert_schedule`**, created at connect/onboarding time: `ingest_gbp_reviews` (24h), `refresh_connection_token` (12h), `publish_sweep` (e.g. 1h), `post_review_replies`/`post_mention_replies` (e.g. 15m), `gbp_reconcile` (24h). |
| `rep_engine/notifications.py` | `check_and_notify`: **add keys to the `created` dict initializer** (`review_needs_reply`); **extend the `drafts_waiting` query** to also COUNT `mention_replies`/`review_replies` in `pending_review`; add a `review_needs_reply` query (negative/new reviews, LIMIT-capped like `neg_mentions`). Event-time kinds (`auto_reply_posted`, `auto_reply_failed`, `connection_revoked`) go through `notify()` directly at the emitting site â€” no `check_and_notify` change for those. |
| `rep_engine/api/routers/content.py` | At `approve()` time, if the work order/brief carries publish channels **and a healthy connection exists**, insert `publish_targets` (no I/O) and enqueue the `publish_sweep` drain. **Graceful fallback:** missing/unhealthy connection â‡’ leave `published_status='pending'` (manual path), never 409 the approval. |
| `requirements.txt` | `cryptography>=42` (pinned with hashes). |
| `.env.example` | `TOKEN_ENC_KEY=`, `AUTOPOST_GLOBAL_ENABLED=false`, provider client secrets. |

### 3.3 New job registrations (`jobs.py`) â€” **drain jobs, one per (business, job_type)**

```python
def _run_publish_sweep(business_id, args):            return _imp("publishing.runner").drain(business_id)
def _run_refresh_connection_token(business_id, args): return _imp("connections.vault").refresh_due(business_id)
def _run_ingest_gbp_reviews(business_id, args):       return _imp("gbp_reviews").ingest(business_id, connection_id=args.get("connection_id"))
def _run_post_review_replies(business_id, args):      return _imp("gbp_reviews").post_approved(business_id)   # drains all 'approved'/'auto_posted_pending'
def _run_post_mention_replies(business_id, args):     return _imp("mention_monitor").post_approved(business_id) # drains owned approved
def _run_gbp_reconcile(business_id, args):            return _imp("gbp_reviews").reconcile(business_id)

JOB_DISPATCH.update({
    "publish_sweep": _run_publish_sweep,
    "refresh_connection_token": _run_refresh_connection_token,
    "ingest_gbp_reviews": _run_ingest_gbp_reviews,
    "post_review_replies": _run_post_review_replies,
    "post_mention_replies": _run_post_mention_replies,
    "gbp_reconcile": _run_gbp_reconcile,
})
# These cap how fast the SWEEP can re-trigger, NOT how many posts happen.
# Per-post volume is enforced by integration_settings daily/hourly caps inside guardrails_ok().
_JOB_RATE_LIMITS.update({
    "publish_sweep": (6, 3600),
    "refresh_connection_token": (4, 3600),
    "ingest_gbp_reviews": (4, 3600),
    "post_review_replies": (12, 3600),
    "post_mention_replies": (12, 3600),
    "gbp_reconcile": (2, 3600),
})
```
> **`[review-fix]`** each `drain()`/`post_approved()` loops, claiming **every** due row for the business (`UPDATE ... WHERE business_id=%s AND status IN (...) AND (next_attempt_at IS NULL OR next_attempt_at<=now()) ... RETURNING *`, one at a time, until none remain). This works *with* the existing `(business_id, job_type)` singleton dedup instead of against it. The rate-limit tuple throttles sweep *triggers*; posting volume is the per-business `daily_autopost_cap`/`hourly_auto_cap`.

### 3.4 New API routers (all registered in `create_app().include_router(...)`)

| Router | Prefix | Endpoints | Auth |
|---|---|---|---|
| `connections_router.py` | `/businesses/{business_id}` (+ **unprefixed** callback) | `GET /connections`; `POST /connections/{kind}/authorize`; `GET /connections/{kind}/callback` (state-scoped, no path id, **no `authorize_business`**); `POST /connections`; `POST /connections/{conn_id}/test`; `DELETE /connections/{conn_id}` | reads `authorize_business`; writes `require_business_editor`; **callback: none (tenancy via `oauth_states`)** |
| `publishing_router.py` | `/businesses/{business_id}` | `GET /assets/{asset_id}/publish-targets`; `POST /assets/{asset_id}/publish`; `POST /publish-targets/{id}/retry` | reads `authorize_business`; writes `require_business_editor` |
| `reviews_router.py` | `/businesses/{business_id}` | `GET /reviews`; `GET /review-replies?status=`; `POST /review-replies/{id}/approve`; `POST /review-replies/{id}/reject`; `PATCH /review-replies/{id}` (edit â†’ deterministic re-screen, `compliance_pass`â†’`None`) | reads `authorize_business`; writes `require_business_editor` |
| `approvals_router.py` | `/businesses/{business_id}` | `GET /approval-queue`; `POST /approval-queue/{kind}/{id}/approve`; `POST /approval-queue/{kind}/{id}/reject`; `GET /integration-settings`; **`PUT /integration-settings`** | reads `authorize_business`; **`PUT` auto-post-enabling fields require `require_org_manager`** |

**Registration & middleware notes (`api/main.py`):**
- Add `app.include_router(...)` for all four routers in `create_app()` alongside the existing block.
- The `/callback` route is intentionally **outside** the `/businesses/{id}` prefix and must **not** depend on `authorize_business`; its tenancy comes solely from `oauth_states`.
- CSRF: the existing double-submit middleware only challenges **cookie-authed, non-bearer, mutating** requests. The GET callback is exempt by method (browser-navigated, single-use state is its CSRF defense); the connect `POST`s are bearer-authed from the SPA, so they pass. Verified against `main.py:147â€“163`.
- All mutating routes are auto-audited by `_audit_writes` (records `user_id, method, path, status` â€” **no body**, so secrets never reach `audit_log`).
- **Owner-tier gate `[review-fix]`:** `PUT /integration-settings` splits â€” toggling `allow_owned_autopost`, `auto_reply_reviews`, `auto_reply_mentions`, `auto_platforms`, or *raising* caps requires `require_org_manager`; benign fields (notify prefs, timezone, disclosure_text) stay `require_business_editor`. Enabling emits a `notify()` and records `updated_by`.
- **Rate-limit / flood control `[review-fix]`:** `POST /connections/{kind}/authorize` (state minting) is capped per business; a TTL sweep prunes expired `oauth_states` so the table cannot be flooded.

---

## 4. Publisher Abstraction

### 4.1 The `Publisher` Protocol (`publishing/base.py`)

Runtime-checkable Protocol. Adapters are **stateless**, receive a decrypted `Connection` + normalized `PublishPayload`, do I/O **through `http.request_json(guard_redirects=True)`**, return a `PublishResult`. They **never touch the DB**; `runner.py` owns all reads/writes.

```python
PayloadKind = Literal["article", "social", "link"]

@dataclass(frozen=True)
class Connection:
    id: int; business_id: int
    provider: str; channel: str
    access_token: str            # decrypted in runner; in-process only, never logged, not retained past publish()
    refresh_token: str | None
    config: dict                 # site_url, wp_user, profile_key, location_id, account_id, site_timezone...

@dataclass(frozen=True)
class PublishPayload:
    kind: PayloadKind
    title: str | None = None; body_html: str | None = None; body_markdown: str | None = None
    tags: list[str] = field(default_factory=list); categories: list[str] = field(default_factory=list)
    featured_image: "MediaItem | None" = None
    text: str | None = None; link_url: str | None = None; media: list = field(default_factory=list)
    scheduled_at: str | None = None       # ISO8601 UTC; None = publish now
    network: str = "_"                    # the single network this target represents
    idempotency_key: str = ""

@dataclass(frozen=True)
class PublishResult:
    status: Literal["live","scheduled","failed"]   # NO 'partial' â€” fan-out is network-grain upstream
    external_url: str | None = None; external_id: str | None = None
    error: str | None = None; retryable: bool = False; retry_after_s: int | None = None

@runtime_checkable
class Publisher(Protocol):
    provider: str
    def capabilities(self, conn: Connection) -> "Capability": ...
    def publish(self, conn: Connection, payload: PublishPayload) -> PublishResult: ...
```
> **`[review-fix]`** because fan-out is now one `publish_targets` row per network, the adapter publishes exactly one network per call and returns a single boolean-ish result â€” there is no `partial` for the runner to explode. `Connection.access_token` is documented as in-process-only and never logged.

### 4.2 Registry (`publishing/registry.py`)

```python
_CHANNELS = {
    "wp_blog":            (WordPressPublisher(),      None),
    "gbp_post":           (GoogleBusinessPublisher(), None),
    "social_fb_page":     (AyrsharePublisher(),       "facebook"),
    "social_ig":          (AyrsharePublisher(),       "instagram"),
    "social_li_org":      (AyrsharePublisher(),       "linkedin"),
    "social_li_personal": (AyrsharePublisher(),       "linkedin"),
    "social_x":           (AyrsharePublisher(),       "twitter"),
    "social_pinterest":   (AyrsharePublisher(),       "pinterest"),
    # social_reddit / yelp deliberately ABSENT: draft-suggestion / read-only only.
}
```
Before enqueuing, the router validates the target connection (a) belongs to the same `business_id`, (b) is `status='active'`, (c) `capabilities()` accepts the asset's `payload_kind`, and (d) for GBP, `gbp_access='approved'`.

### 4.3 Concrete adapters

**`WordPressPublisher`** (`provider='wordpress'`)
- Auth: HTTP Basic Application Password over **HTTPS-only** (`.org`) or OAuth2 bearer (`.com`), branch on `conn.config['variant']`.
- **All requests via `http.request_json(... , guard_redirects=True)`** which calls `netguard.assert_url_allowed` and re-validates each redirect hop (no SSRF to `169.254.169.254`, RFC1918, localhost). Non-https `.org` site_url rejected at connect.
- Article flow: upload `featured_image`â†’`media_id`; resolve tag/category namesâ†’IDs; two-phase `draft`â†’`publish` so a half-built post is never live.
- **Scheduling timezone `[review-fix]`:** scheduled posts are sent via **`date_gmt`** (UTC) â€” never the site-local `date` field â€” so the wall-clock is correct on non-UTC sites. `Capability(article=True, link=True, schedule=True, draft_then_publish=True)`.
- Errors run through `vault._redact()` before they touch `last_error`/`publish_attempts.error`.

**`AyrsharePublisher`** (`provider='ayrshare'`, ONE adapter, **one network per call**)
- Auth: `Authorization: Bearer <AYRSHARE_API_KEY>` (env) + `Profile-Key: <tenant profile_key>` (encrypted). Host pinned to `api.ayrshare.com`.
- One `POST /api/post` scoped to a single network (the target's `network`). The runner created one target per network, so there is no per-call fan-out and no partial collapse. Re-running a network never re-posts a live sibling (network-grain idempotency key).
- IG 25/24h cap, X per-post cost surfaced via `capabilities()`/UI.

**`GoogleBusinessPublisher`** (`provider='google_business'`, local Posts only)
- `POST .../locations/{locationId}/localPosts`, scope `business.manage`, host pinned. Distinct from review replies (Â§6). Blocked in UI until `gbp_access='approved'`.

### 4.4 The publish drain (`publishing/runner.drain`)

`runner.drain(business_id)` loops until no claimable rows remain. Per iteration:

1. **Claim atomically, joined on connection health:**
```sql
UPDATE publish_targets SET status='publishing', attempts=attempts+1, updated_at=now()
WHERE id = (
  SELECT id FROM publish_targets
  WHERE business_id=%s AND status IN ('queued','failed','scheduled')
    AND (next_attempt_at IS NULL OR next_attempt_at<=now())
    AND connection_id IN (SELECT id FROM platform_connections
                          WHERE business_id=%s AND status='active')
  ORDER BY next_attempt_at NULLS FIRST, id
  FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING *;
```
   No row â‡’ break (loop done). A target whose connection is revoked/inactive is **not** claimed (it was already moved to `needs_reconnect` on revoke â€” see Â§7.5).
2. **Idempotency short-circuit:** if this slot already has an `external_id`, mark `skipped`.
3. Load `platform_connections`, `conn.commit()` to release the row lock before slow I/O.
4. `_to_connection(row)` decrypts in-process; `_build_payload(t)`; `adapter_for(channel).publish(...)` â€” the only external write.
5. Write a **redacted** `publish_attempts` row, branch:
   - `live`/`scheduled` â†’ update target; **write back to `assets`** (`UPDATE assets SET published_url=%s, published_status='live' WHERE id=%s AND business_id=%s`). Canonical URL = the article target; social link posts update per-network rows but don't overwrite the canonical URL.
   - `retryable` and `attempts < _MAX_ATTEMPTS` â†’ `status='failed'`, `next_attempt_at = now() + (retry_after_s or jittered backoff)` (honor `Retry-After` on 429).
   - **401 / `invalid_grant`** â†’ mark the connection `revoked`, move its dependent queued/scheduled targets to `needs_reconnect`, `notify(connection_revoked)`, stop retrying.
   - terminal failure â†’ `status='failed'`, `check_and_notify`/`notify("publish failed")`.
6. **Global kill switch:** before any auto-driven post, the drain checks `AUTOPOST_GLOBAL_ENABLED`; off â‡’ owned auto-posts are held as `pending_review` and skipped (manual publishes still allowed).

**Self-heal:** a target stuck in `publishing` past a timeout is reset (mirrors `reap_stale()`). **Scheduling:** `scheduled_for` â†’ `status='scheduled', next_attempt_at=scheduled_for`; **a reconcile pass flips WP.com server-scheduled posts to `live`** (those fire no webhook) by polling the post id â€” shipped in the same phase as scheduling, not later.

### 4.5 Replacing manual entry

At `approve()` time, if the work order/brief specifies publish channels **and** a healthy connection exists, the content router inserts network-grain `publish_targets` (no I/O) and enqueues `publish_sweep`. `approve()` copies the draft's `compliance_pass` onto the asset; the runner re-checks `compliance_pass IS TRUE` before an auto-post. Manual `PATCH /assets/{id}` remains for non-integrated sites. **The publisher trusts that a human approved, not that the LLM passed** â€” for the auto path the strict `pass IS True` predicate (excluding `None`) is what guarantees compliance.

> **Open item:** publish-channel source â€” existing work-order field, a new `work_orders.publish_channels TEXT[]`, or derive from `amplification_playbook`? Flagged; not blocking the schema.

---

## 5. Response Approval Queue

### 5.1 Surface classifier (`response_policy.classify_surface`)

Every actionable item resolves to exactly one `surface`: **`owned`** (a property the tenant controls with a verified `platform_connections` row) or **`third_party`** (anyone else's surface â€” auto-posting forbidden). Classification = source + URL host + connection match; absence of a match degrades safely to `third_party`.

| `mention.source` | Default | Refinement |
|---|---|---|
| `reddit` | `third_party` | **Always** third_party. |
| `news_rss` | `third_party` | Usually `do_not_engage`. |
| `web` | `third_party` | `owned` iff host matches a tenant connection domain. |
| `social` | `third_party` | `owned` iff on the tenant's own page AND a matching meta/linkedin connection exists. |
| `reviews` | `third_party` | **GBP-connected location â†’ handled by `gbp_reviews`, NOT surfaced as a mention** (cross-dedup). Yelp/Trustpilot stay third_party. |

### 5.2 Owned-vs-third-party decision table (`response_policy.route`)

| surface | opted in? | `compliance_pass` | within guardrails? | `auto_policy` | What happens | Reviewer actions |
|---|---|---|---|---|---|---|
| `owned` | yes | `True` | yes | **`auto_eligible`** | Set approvedâ†’enqueue drain; post via connection; record `posted_at`/`external_post_id`/`posted_by='auto'`; owner notified after. | (read-only audit; can retract) |
| `owned` | yes | `True` | **no** | `manual` | Queued. | Approve(=post), Edit, Dismiss, Open |
| `owned` | yes | `False`/`None` | â€” | `manual` | Compliance fail-safe. | Approve(after edit re-screens), Edit, Dismiss, Open |
| `owned` | **no** | any | â€” | `manual` | Queued. | Approve(=post), Edit, Dismiss, Open |
| `third_party` | irrelevant | any | â€” | **`manual` (forced)** | **DRAFT + ALERT ONLY.** | Approve(=mark handled offline), Edit(copy), Dismiss(=do-not-engage), Open. **NO post button.** |

Coded rules:
1. `third_party` â‡’ `manual` unconditionally; UI omits the post control.
2. `owned` â‡’ `auto_eligible` only if ALL: `AUTOPOST_GLOBAL_ENABLED`; `allow_owned_autopost` (org-manager-enabled) and platform in `auto_platforms`; `comp["pass"] is True`; sentiment not in `never_auto_sentiments`; `guardrails_ok()` (daily/hourly caps + quiet hours **evaluated in `business_timezone`**, `auto_reply_max_len`, `banned_phrases`, `warmup_manual_count`).
3. Compliance authoritative + fail-safe (`False`/`None` â‡’ `manual`).

### 5.3 Unified queue (read model, `response_policy.list_queue`)

No new table â€” assembled server-side at `GET /approval-queue`, merging `mention_replies` (`pending_review`), `review_replies` (GBP, owned, from the dedicated table), and scheduled `publish_targets` (read-only). **`[review-fix]` cross-dedup by `(source, external_id)`** when normalizing into `QueueItem` so a Google review surfaced via both shapes is one item. Filters: `surface`, `sentiment`, `platform`, `status`, `kind`. The hook polls only while a feeding job is in flight.

### 5.4 State machines (reconciled with the existing code `[review-fix]`)

The existing code uses `mention_replies.status âˆˆ {pending_review, approved, rejected}` and `mentions.status âˆˆ {new, actioned}`, read by `list_pending` (`pending_review`) and `check_and_notify` (`mentions.status='new'`). The new model **extends, not replaces**:

- **`mention_replies`:** `pending_review â†’ approved` (owned Approve; `posted_by`/`posted_at` set on drain success; a sub-state `posted` recorded via `posted_at IS NOT NULL`) | `pending_review â†’ approved` with `handled` semantics for third_party Approve (no post) | `pending_review â†’ rejected` (Dismiss) | owned auto path: `auto_eligible â†’ approved â†’ (drain) â†’ posted`, and a failed drain **degrades back to `pending_review`** (human safety net). `mentions.status='actioned'` on any approve (unchanged).
- **`review_replies`:** `(draft+compliance) â†’ pending_review â†’ approved â†’ (post_review_replies drain) â†’ posted`, or guardrail-pass â†’ `auto_posted_pending â†’ (drain) â†’ auto_posted` / failure â†’ `pending_review`. `rejected`/`superseded` terminal.
- **`publish_targets`:** `queued â†’ publishing â†’ live` (or `â†’ failed â†’ backoff â†’ queued`), plus `scheduled`/`skipped`/`canceled`/`needs_reconnect`.

**Readers updated in lock-step:** `list_pending` unchanged (still `pending_review`); `check_and_notify` `drafts_waiting` query extended to also count `mention_replies`/`review_replies` in `pending_review`; a new `review_needs_reply` query added; console reads the new sub-states.

**Invariant restated:** the only no-human transitions to a public post are `auto_eligibleâ†’...â†’posted` (mentions, owned) and `auto_posted_pendingâ†’auto_posted` (reviews, owned). Every other path requires a human Approve.

### 5.5 Notifications

- Negative **third-party** mention (discover-time): `notify(kind="negative_mention", severity="high", dedup_key=f"neg-mention:{id}")` â€” nothing posted.
- Owned negative **review**: `kind="review_needs_reply"`, high â€” queued, never auto.
- `check_and_notify`: **`created` dict gains `review_needs_reply`**; `drafts_waiting` now also counts mention/review replies in `pending_review`.
- Event-time via `notify()`: `auto_reply_posted` (low, transparency), `auto_reply_failed` (warn, degrade-to-human), `connection_revoked` (warn, on hard refresh failure **and runtime 401**).

### 5.6 FTC / audit posture

- Replies stored as **brand replies**. **Deterministic checks in `reply_compliance.py` run on every reply** (first-person-customer voice, solicitation/incentive, impersonation); the LLM screen no longer auto-passes replies as non-financial. Until shipped, all reply paths are forced `manual`.
- Full trail: who drafted (system/LLM), who approved (`reviewer` human-readable string â€” existing convention â€” or `'auto'` with the settings snapshot), who posted (`posted_by`), when (`posted_at`), the exact text (`draft`), the proof (`external_post_id`/`external_ack`), and the **`edits` JSONB** append-log. The numeric authoritative actor is `audit_log.user_id`; `reviewer`/`posted_by` are the human-readable mirror.

### 5.7 GDPR / retention `[review-fix]`

- `gbp_reconcile`/a mentions reconcile job re-checks source presence: a review/mention whose source content disappeared is soft-deleted (`status='gone'`) and excluded from auto-reply (stale sentiment can't drive a post).
- Once a reply is drafted, **author PII is redacted** from the durable store (`author_pii_redacted=TRUE`, author replaced with a stable hash) â€” the brand reply needs no author identity afterward.
- A documented retention window for third-party author content; `gdpr.delete_business` already cascades all scoped rows (auto-discovered), and the new tables inherit the `business_id` CASCADE so per-business erasure covers them.

---

## 6. Google Review Reply Path

GBP reviews are a **distinct owned surface** with a structured reply API (`reviews.updateReply`) â€” the only thing legitimizing a *guarded* opt-in auto-reply. Yelp/Facebook = monitor-only.

### 6.1 `ingest_gbp_reviews` job

`gbp_reviews.ingest(business_id, connection_id)`:
1. Resolve the connection (`kind='google_business_profile'`); `vault.access_token(conn_id)`; read `location_ref`. **Gate on `gbp_access='approved'` and location still verified/owned** (connection health) â€” else skip with a clear status.
2. `GET {GBP_BASE}/{location}/reviews` **via `http.request_json(guard_redirects=True)`, host-pinned**, **paginating `nextPageToken`** (must loop, not first-page-only).
3. Per review: `INSERT ... ON CONFLICT (dedup_hash) DO UPDATE` â€” when GBP `updateTime` advances, **reset `status='new'`** so an edited review (5â˜…â†’1â˜…) is re-drafted; map star enum; derive sentiment (`â‰¤2 negative, 3 neutral, â‰¥4 positive`); refresh `last_seen_at`.
4. **`_draft_pending`:** for `status='new'`, **fence every untrusted field (author, title, body)** with `_fence_untrusted`, draft via `content_generator.draft_reply(REVIEW_SYSTEM, payload)`, run `_compliance` (now including the reply screen), INSERT `review_replies`, set initial status via the guardrail predicate (Â§6.3). Redact author PII after drafting.
- Recurrence via `upsert_schedule(business_id, "ingest_gbp_reviews", interval_hours=24)`.

### 6.2 Reply-on-approve + posted-reply edits

Approval flips `review_replies.status='approved'` and enqueues the `post_review_replies` **drain** (network I/O = job). `gbp_reviews.post_approved(business_id)` loops over `approved`/`auto_posted_pending` rows, **each scoped `WHERE id=%s AND business_id=%s` and verifying `connection.business_id == business_id` before decrypt**, does `PUT {GBP_BASE}/{location}/reviews/{ext_id}/reply` (host-pinned, guarded), stores the **redacted** raw response in `external_ack`, sets `posted`/`auto_posted`, and `reviews.status='replied'`. Refuses to post if `compliance_pass is False`.

**`[review-fix]` one-reply-per-review semantics:** GBP `updateReply` is an UPSERT â€” a second reply silently replaces the first. **Editing a posted reply** is modeled as a re-PUT: the old row goes `superseded`, a new `review_replies` row carries the new text and a fresh `external_ack`. This ships **before** auto-reply is enabled.

### 6.3 Owned-surface auto-reply guardrails

Default human approval; auto-reply is opt-in (org-manager) and fires only for clearly-safe, positive, short replies:
```python
def _auto_reply_ok(s, rv, draft, comp) -> bool:
    return (s.auto_reply_reviews
        and AUTOPOST_GLOBAL_ENABLED
        and comp.get("pass") is True
        and rv.get("star_rating") is not None and rv["star_rating"] >= s.auto_reply_min_stars
        and rv.get("sentiment") != "negative"
        and bool(rv.get("body"))                     # require non-empty review comment (no rating-only auto)
        and bool(draft) and not draft.startswith("[DRAFT")
        and "[INSERT:" not in draft
        and len(draft) <= s.auto_reply_max_len)
```
A failed auto-post degrades to `pending_review`. Permanent audit distinction: human (`posted`, `reviewer=<user>`) vs machine (`auto_posted`, `reviewer='auto'`).

**Domain gaps closed:** rating-only 5â˜… require a non-empty comment; edited reviews re-draft via `ON CONFLICT DO UPDATE` (status reset on `updateTime` advance) **before** auto-reply default-on; posted-reply edits via re-PUT/`superseded`; allowlist gate (`gbp_access`) **disables auto-reply in the UI until approved**; review-deletion handled via `status='gone'` reconcile; location ownership re-checked before posting.

---

## 7. Connections Vault

### 7.1 Crypto-at-rest (`rep_engine/crypto.py`)

Only reversible-crypto seam. Key in env `TOKEN_ENC_KEY` (never in Postgres; rules out `pgcrypto`). `MultiFernet` for rotation (keys[0] encrypts, all decrypt).

```python
def _fernet() -> MultiFernet:
    raw = os.getenv("TOKEN_ENC_KEY", "").strip()
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise RuntimeError("TOKEN_ENC_KEY is not set ... generate: python -c "
            "\"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
    if os.getenv("JWT_SECRET", "") in keys:
        raise RuntimeError("TOKEN_ENC_KEY must not equal JWT_SECRET (separate blast radius).")
    return MultiFernet([Fernet(k.encode()) for k in keys])
```
- **`[review-fix]` lifecycle:** a lightweight startup probe logs a WARN and sets a `/health` degraded flag if `TOKEN_ENC_KEY` is unset (Stripe-parity: not a hard boot failure, but visible before the connect UI goes live). `TOKEN_ENC_KEY != JWT_SECRET` asserted. A `rotate_token_keys` CLI/job decrypts-with-any/re-encrypts-with-`keys[0]` across `platform_connections` so retired keys can be dropped. Documented to live in a secrets manager, not the image.
- **`vault.py` is the only importer of `crypto`** â€” asserted by a CI grep test.
- **Never-log-secrets:** decrypted dicts never cross `log.*`; `_redact()` strips `Bearer`/`Basic`/`app_password`/`token=`/`X-*` patterns and is applied to **every** `*_error`/`*_summary`/`external_ack` field before persist (connection, publish_attempts, review_replies). A test asserts a known token never appears in any such column.

### 7.2 OAuth2 connect flow

- **`POST /connections/{kind}/authorize`** (`require_business_editor`, per-business minting cap) â†’ `{authorize_url}`. `oauth.build_state()` mints `secrets.token_urlsafe(>=128 bits)`, HMAC-signs it **domain-separated** (`HMAC(secret, b"oauth-state|"+state)`; prefer a dedicated `OAUTH_STATE_SECRET`, else `JWT_SECRET`), persists a 10-min `oauth_states` row. Provider builds the consent URL with **minimum scopes** (see open item on narrowing GBP `business.manage`).
- **`GET /connections/{kind}/callback`** (unprefixed, no `authorize_business`): `DELETE FROM oauth_states WHERE state=%s RETURNING *` (single-use, in the same txn as the code exchange) â†’ **403** if absent/expired; verify HMAC with `hmac.compare_digest`; recover `business_id`. **The post-callback redirect is a fixed internal path keyed by platform â€” a client-supplied `redirect_uri` is never reflected** (no open redirect). Exchange code (token endpoint host-pinned + guarded) â†’ `vault.upsert_connection(... encrypt first ...)` â†’ `notify("Connected {platform}")`.

### 7.3 Non-OAuth connect flows

One body-typed `POST /connections`, `token_type` discriminates:
- **WordPress app-password** (`app_password`): `{site_url, wp_user, app_password}`; verify via `GET /wp-json/wp/v2/users/me` Basic **over HTTPS-only, through `netguard`** (reject non-https and private IPs); store secret in `access_token_enc`, `meta={site_url,wp_user,site_timezone}`.
- **Ayrshare profile-key** (`ayrshare_profile`): `{profile_key, display_name}`; only the per-client key is stored encrypted.
- **Google OAuth** (`google_oauth`): the OAuth2 flow; surfaces `gbp_access='pending'` until allowlist approval.

### 7.4 Token refresh (`refresh_connection_token` drain)

Sweeps `status='active' AND expires_at < now()+24h`, refreshes (host-pinned, guarded), re-encrypts. Hard failure â†’ `status='revoked'`, redacted `last_error`, `notify('connection_revoked')`, **and dependent queued/scheduled targets â†’ `needs_reconnect`**. Transient â†’ `status='error'`, keep token, retry. A `revoked`/`error` connection is excluded from publishing (runner claim join). **`[review-fix]`** because long-idle refresh tokens can die before the 24h window, a runtime 401/`invalid_grant` during any publish/reply immediately triggers the same revoke+notify+`needs_reconnect`+UI "Reconnect to post" path; the 12h sweep also does a liveness probe even when `expires_at` is far out.

### 7.5 Tenant isolation

- Every business-prefixed handler **and every post job** re-passes `business_id` into `WHERE`, and post jobs additionally verify `connection.business_id == business_id` before decrypt (fail closed on mismatch). A test asserts a cross-business `reply_id` returns 0 rows. The legacy `mention_monitor.approve()/reject()` are retrofitted to `WHERE id=%s AND business_id=%s`.
- The `/callback` tenancy rests solely on the HMAC-signed, single-use, TTL'd `oauth_states` row.
- `connected_by` records the actor; the connection belongs to the **business**.
- `GET /connections` returns a redacted DTO (no `*_enc`). `DELETE` â†’ `status='revoked'`, **zeroes both `*_enc`**, moves dependent queued/scheduled targets to `needs_reconnect`, attempts provider-side revoke (failure is fine â€” local revoke + zeroed ciphertext is fail-safe; the row is still excluded from publishing).
- **Residual risk (documented):** one global `TOKEN_ENC_KEY` = same trust tier as `JWT_SECRET`; a key compromise exposes all tenants. Acceptable for v1; future hardening = per-tenant key derivation `HKDF(TOKEN_ENC_KEY, business_id)` so a leaked ciphertext still needs the `business_id` binding.

---

## 8. Console (`reputation-console`)

### 8.1 Connections page (`/integrations` â†’ Connections tab)
Extend the existing Integrations page with two tabs â€” **Connections** (new) and **Imported reports** (existing). Each provider = a `Card` with a status `Pill`, last-checked timestamp, role-gated actions behind `useBusiness().canEdit`. `ConnectModal` branches by `auth_kind`: `oauth` â†’ redirect; `app_password` â†’ HTTPS-scoped form.

| Platform | `capability` | Console action |
|---|---|---|
| WordPress (.org/.com) | `publish` | Approve & Post (owned blog) |
| Google Business Profile | `review_reply` | Approve (auto-posts reply via GBP) â€” **"posts publicly now" confirm**; **disabled until `gbp_access='approved'`** |
| FB / IG / LinkedIn / Pinterest (Ayrshare) | `publish` | Approve & Post (owned page) |
| X / Twitter | `publish_costed` | Approve & Post + **cost note** |
| Reddit | `alert_only` | Open on platform + Copy draft + **ToS-responsibility notice** |
| Yelp | `alert_only` (read-only) | Open + Copy draft + ToS notice |

### 8.2 Unified Approval Queue (`/approvals`)
New page in the **Watch live** Sidebar group (after Mentions). Tabs: **Review replies (n) | Mention replies (n) | Scheduled posts (n)**. `QueueItemCard` branches by `item.capability`:
- `alert_only` â†’ "Alert only" badge, read-only draft, **Open on platform** + **Dismiss** + **Copy draft** (+ ToS notice), **no post button**.
- `review_reply` â†’ Approve (auto-posts, with confirm) + Reject.
- `publish*` â†’ Approve & Post + Reject; if the connection is `expired`/`needs_reconnect`, swap Approve for **"Reconnect to post"** â†’ `/integrations`.
- `compliance.pass === false` â†’ approve **disabled** (tooltip); `=== null` â†’ amber "needs human review" pill, approve allowed.
- **Auto-post enablement toggles (settings)** are visible/enabled only to org-manager+ roles; a "posts on your behalf" confirm is required to arm them.
- **Fails closed:** unknown/missing capability is treated as `alert_only`.

### 8.3 Publish controls (asset detail)
`AssetPublishPanel`: `ChannelPicker` offers only **connected, healthy, capability-matched** channels (unconnected â†’ "connect first â†’"). `ScheduleControl` (Publish now | Schedule for, shown in the business timezone). `usePublishAsset` enqueues `publish_sweep` (never inline), polls `useJobs` in-flight-only, flips the tile to **live** with the written-back URL. `usePatchAsset` retained as manual fallback.

### 8.4 `types.ts` additions
`Connection`, `ConnectionStatus` (`pending|active|expired|error|revoked|needs_reconnect`), `ConnectionAuthKind`, `Capability` (`publish|publish_costed|review_reply|alert_only`), `ComplianceInfo`, `Review`, `ReviewReply`, `MentionReply`, `PublishTarget`, `QueueItem` (`kind: review_reply|mention_reply|scheduled_post`, with `editable`, `can_auto_post`, `surface`), `ApprovalQueue`, `IntegrationSettings`. Nullable fields `T | null`.

### 8.5 `hooks.ts` additions
`useConnections`, `useConnectAppPassword`, `useTestConnection`, `useDisconnectConnection`; `useApprovalQueue` (poll only while feeding jobs in flight), `useApproveReply`, `useRejectReply`, `useEditReply`; `useReviewReplies`/`useApproveReviewReply`/`useRejectReviewReply`/`useEditReviewReply`; `usePublishTargets`, `usePublishAsset`, `useRetryTarget`; `useIntegrationSettings` (`GET/PUT`).

### 8.6 Sidebar (`Sidebar.tsx`)
```ts
// In "Watch live", after Mentions:
{ href: "/approvals", label: "Needs your approval", opLabel: "Approval queue" }
// Settings /integrations (optional clearer wording):
{ href: "/integrations", label: "Connections & imports", opLabel: "Integrations" }
```

---

## 9. Migrations (`0040`â†’`0044`)

Apply order `0040 â†’ 0041 â†’ 0042 â†’ 0043 â†’ 0044`. Verified project style: `from __future__ import annotations`, module-level `revision`/`down_revision`/`branch_labels=None`/`depends_on=None`, idempotent `CREATE TABLE/INDEX IF NOT EXISTS` + `ADD COLUMN IF NOT EXISTS`, `REFERENCES businesses(id) ON DELETE CASCADE`, contentâ†’connection FKs `ON DELETE SET NULL`, `TIMESTAMPTZ DEFAULT now()`, `JSONB DEFAULT`. Chain head `0039_super_admin_billing_flags`; each `down_revision` = prior file's `revision`.

| File | Creates / alters | Notes |
|---|---|---|
| `0040_platform_connections.py` | `platform_connections` (+ business/kind/expiry/**partial-active** indexes) **and `oauth_states`** | down_revision `0039_super_admin_billing_flags`. Split-secret columns, `gbp_access`, `site_timezone` via `meta`. |
| `0041_publish_targets.py` | `publish_targets` + `publish_attempts` + `ALTER TABLE assets ADD COLUMN compliance_pass` | **Network-grain**: `network NOT NULL DEFAULT '_'`, `UNIQUE(asset_id,channel,connection_id,network)`, `uq_publish_targets_idem`, `next_attempt_at`, `needs_reconnect` status, `work_order_id`. |
| `0042_reviews.py` | `reviews` + `review_replies` | `review_updated_at`, `author_pii_redacted`, `last_seen_at`, `status='gone'`, `external_ack`, `edits`, `superseded` status, `uq_review_replies_active`. |
| `0043_mention_queue_ext.py` | **Formalizes** `monitor_keywords`/`mentions`/`mention_replies` (byte-for-byte with `_ensure()`), then `ADD COLUMN IF NOT EXISTS` surface/connection/auto_policy/posted_*/PII cols | FK adds wrapped in `DO $$ â€¦ EXCEPTION WHEN duplicate_object/undefined_table`. `auto_policy DEFAULT 'manual'` (`manual|auto_eligible`). **Asymmetric downgrade** drops only added cols/constraints. **`mention_monitor._ensure()` updated with the same ADD COLUMN set + parity test.** |
| `0044_integration_settings.py` | `integration_settings` (PK `business_id`) | All guardrail fields + `business_timezone` + `third_party_weekly_draft_cap`. Default OFF/safe. **Onboarding inserts the OFF row; readers COALESCE if absent.** |

Files (absolute):
- `c:\Users\asbur\Koob_Reputation_Management\reputation_engine\alembic\versions\0040_platform_connections.py`
- `c:\Users\asbur\Koob_Reputation_Management\reputation_engine\alembic\versions\0041_publish_targets.py`
- `c:\Users\asbur\Koob_Reputation_Management\reputation_engine\alembic\versions\0042_reviews.py`
- `c:\Users\asbur\Koob_Reputation_Management\reputation_engine\alembic\versions\0043_mention_queue_ext.py`
- `c:\Users\asbur\Koob_Reputation_Management\reputation_engine\alembic\versions\0044_integration_settings.py`

---

## 10. Build Order / Sequencing

**Buy-vs-build:** **Ayrshare** for all social (one adapter/API, hosted account-linking); **Direct** for WordPress (stable REST, Application Passwords) and **GBP** (no aggregator offers review-reply + local posts). **Reddit/Yelp = never auto** (no safe write API / ToS) â€” draft + alert only.

### Phase 0 â€” Compliance & safety primitives (prerequisite)
`reply_compliance.py` deterministic FTC checks + extended `COMPLIANCE_SYSTEM`; `AUTOPOST_GLOBAL_ENABLED` flag; `crypto.py` (+`cryptography>=42` pinned, `TOKEN_ENC_KEY`, `!= JWT_SECRET`, health probe); `_redact()` everywhere. **No reply path can auto-post until this lands.**

### Phase 1 â€” Vault foundation (no posting yet)
Migration `0040`, `connections/` (vault + oauth + WP app-password + Google OAuth providers, **all I/O via `netguard`/`http`**), `connections_router.py` (+ registered in `main.py`, callback unprefixed), Console **Connections** tab, `refresh_connection_token` drain + a `schedules` row at connect time. Outcome: connect WP/GBP; nothing posts. Guardrails: secrets encrypted, redacted logs/DTOs, single-use domain-separated OAuth state, no open redirect, SSRF-guarded verify.

### Phase 2 â€” Publishing to owned WordPress
Migration `0041` (incl. `assets.compliance_pass`), `publishing/` (base + registry + `WordPressPublisher` + `runner.drain`), `publish_sweep` drain + schedule, `publishing_router.py` (registered), asset publish panel, write-back, **WP.com scheduled-post reconcile in this same phase**, `content.approve()` enqueues network-grain targets (graceful fallback when no healthy connection). Outcome: approved articles auto-publish to the client's own blog with the real URL. Guardrails: `compliance_pass IS TRUE` at publish, network-grain idempotency, connection-health claim join, `date_gmt` scheduling.

### Phase 3 â€” GBP review ingestion + human-approved replies
Migration `0042`, `gbp_reviews.py` (`ingest` paginated + `_draft_pending` fencing all fields + `post_approved` drain + `reconcile`), shared `draft_reply()`, `ingest_gbp_reviews`/`post_review_replies`/`gbp_reconcile` drains + schedules, `reviews_router.py` (registered). **Auto-reply OFF.** Outcome: reviews flow into the queue; human approves; reply posts with `external_ack` proof; posted-reply edits via re-PUT/`superseded`; edited-review re-draft live. Guardrails: allowlist gate as connection state, location-ownership re-check, FTC brand-reply checks, author-PII redaction.

### Phase 4 â€” Unified Approval Queue + surface routing
Migration `0043` (+ `_ensure()` parity), `response_policy.py`, extend `mention_monitor` (business-scoped `approve`/`reject`, surface routing, reviews cross-dedup, `_ensure()` mirror), `approvals_router.py` (registered), `/approvals` page, Sidebar entry, notification wiring (`drafts_waiting`/`review_needs_reply`). Outcome: one inbox; third-party = draft+alert+copy; owned = approve-to-post. Guardrails: `third_party` forced `manual`; Reddit/Yelp always third-party; `alert_only` fails closed; optional per-platform draft caps + ToS notice.

### Phase 5 â€” Social fan-out + opt-in owned auto-reply
`AyrsharePublisher` (one network per call), `GoogleBusinessPublisher` (local posts), social channels in the picker, X cost hint. Migration `0044` + `GET/PUT /integration-settings` (**auto-post-enabling fields gated `require_org_manager`**) + Console toggles + **`AUTOPOST_GLOBAL_ENABLED`** kill switch wired into the runner. Enable opt-in owned auto-reply only after warm-up ramp, edited-review re-draft, allowlist approval, and the FTC checks are all in place. Guardrails: auto-post only `owned`+opted-in+`pass IS True`+caps/quiet-hours(in tz)/warmup+global flag; `blocked_channels`/`auto_platforms` validated at the settings layer; every auto-post emits `auto_reply_posted`; failures degrade to `pending_review`.

---

## 11. Resolved review findings (ledger)

**Convention-fit fixes**
- Per-`(business, job_type)` dedup is real â†’ replaced all per-item jobs with singleton **drain** jobs that claim every due row; exactly-once lives on the content-row status claim. (`jobs.py:282â€“308`)
- Mention status vocabularies reconciled with existing `approved/rejected/actioned`; `list_pending`, `check_and_notify`, console updated in lock-step. (`mention_monitor.py:561â€“596`, `notifications.py:79â€“99`)
- All four routers explicitly `include_router`'d in `create_app()`; callback unprefixed + no `authorize_business`; CSRF GET-exempt confirmed. (`main.py:147â€“236`)
- Corrected scheduler path to `rep_engine/scheduler.py`; recurrence requires `schedules` rows via `upsert_schedule` (`DEFAULT_CADENCES` is cosmetic). (`scheduler.py:32,48,74`)
- `assets` gains `compliance_pass` (copied in `approve()`); runner re-checks it â€” fixes "assets has no compliance column." (`content_generator.py:549â€“614`)
- `_ensure()` updated with the 0043 `ADD COLUMN IF NOT EXISTS` set + parity test (fresh-DB drift). (`mention_monitor.py:58â€“73`)
- `_JOB_RATE_LIMITS` documented as sweep-trigger caps, distinct from per-post `integration_settings` caps.

**Domain/coverage fixes**
- FTC checks are now real code (`reply_compliance.py`) + extended `COMPLIANCE_SYSTEM`; replies forced `manual` until shipped. (`content_generator.py:281â€“305`)
- GBP edit-after-post (re-PUT/`superseded`), one-reply UPSERT semantics, edited-review re-draft, review-deletion `gone` reconcile, location-ownership re-check.
- Timezone correctness: WP `date_gmt`, `business_timezone` source of truth, WP.com scheduled-post reconcile in the scheduling phase.
- Network-grain fan-out idempotency (no NULL-network parent).
- Cross-dedup of a Google review appearing as both `reviews` and a Serper mention.
- `integration_settings` auto-created OFF at onboarding + COALESCE-to-safe-default reads; `approve()` graceful fallback with no healthy connection.
- GDPR: reconcile/erasure job, author-PII redaction, retention window, CASCADE coverage.
- Per-connection rate-limit intent + shared-platform-quota awareness flagged (see open items); Reddit/Yelp engagement caps + ToS notice.

**Security fixes**
- SSRF guard on every outbound call via `http.request_json(guard_redirects=True)` / `netguard.assert_url_allowed` + host allowlist; https-only WP.
- Edit re-screen semantics matched to code (deterministic in-request, `passâ†’None`, full LLM re-screen in a job).
- Post jobs re-scope by `business_id` + verify `connection.business_id`; legacy `approve()/reject()` retrofitted.
- Owner-tier (`require_org_manager`) gate on auto-post enablement + a platform-global `AUTOPOST_GLOBAL_ENABLED` kill switch.
- Redaction over every error/summary/`external_ack` field; `vault.py`-only crypto import (CI grep).
- OAuth: no open redirect (fixed internal path), `token_urlsafe(â‰¥128 bits)` + `compare_digest` + domain-separated HMAC (prefer `OAUTH_STATE_SECRET`), single-use `DELETE...RETURNING` in the exchange txn, authorize-endpoint mint cap + TTL sweep.
- `TOKEN_ENC_KEY` lifecycle: startup health probe, `!= JWT_SECRET` assertion, `rotate_token_keys` CLI, secrets-manager guidance.
- Runtime-401 â†’ immediate reconnect-needed surfacing (not only the 24h sweep).
- `Connection.access_token` documented as in-process-only, never logged.

### Decisions locked (owner, 2026-06-24)
1. **Social layer → BUY Ayrshare** (one API + hosted account-linking; hybrid migration to direct OAuth left open for later if vendor cost justifies it).
2. **Launch scope → all three tracks in scope**, built in the §10 order: WordPress + GBP first (Phases 1–3), then the unified mention/approval queue (Phase 4), then social fan-out (Phase 5).
3. **Automation posture → all auto-post OFF by default**, org-manager opt-in per channel. No pre-enabled auto-reply tier.
4. **Third-party (Reddit/Yelp/forums) → DRAFT a suggested reply for human review** (copy-paste-ready, human still decides whether to engage). Resolves former open-Q9: `third_party_engage_default='draft_alert'` keeps drafting; the queue still forbids any auto-post button on third-party items.

### Genuinely-open questions still for the owner
1. **Publish-channel source:** existing work-order field, new `work_orders.publish_channels`, or derived from `amplification_playbook`?
2. **Billing:** should `publish`/X pay-per-post count against a billing quota, or is rate-limiting + caps sufficient?
3. **GBP scope minimization:** is there a narrower GBP scope than `business.manage` that still covers read-reviews + reply + local posts? Request the minimum if so.
4. **Per-tenant key derivation:** adopt `HKDF(TOKEN_ENC_KEY, business_id)` now, or accept the single-key v1 trust tier?
5. **Shared platform-app quotas** (Ayrshare monthly cap, X tier, GBP QPM): add global quota accounting now, or rely on per-business caps + backoff for v1?