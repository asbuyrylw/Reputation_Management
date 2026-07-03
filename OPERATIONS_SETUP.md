# Operations & Setup Guide — what you need to run this in production

This is the complete list of **API keys, third-party services, integrations, and per-client data**
needed to make the platform work as designed. It's organized in tiers: get **Tier 0 + Tier 1**
working first (that's "the product runs"), then enable the per-feature integrations in **Tier 2** as
you need them. Everything is **dormant-safe** — a feature with no key set simply no-ops (it never
crashes), so you can light these up one at a time.

All keys go in `reputation_engine/.env` (copy from `.env.example`). After changing `.env`, restart
the API + worker.

---

## Tier 0 — Infrastructure (REQUIRED)

| What | Env var(s) | How to get it / notes |
|---|---|---|
| **PostgreSQL database** | `REP_DB_DSN` | A Postgres 14+ instance. **Local dev: `docker compose -f docker-compose.db.yml up -d`** — a durable `rep_pg_test` container on `:15432` backed by the **named** volume `rep_pg_data` (survives container recreate). Production: any managed Postgres (RDS, Supabase, Neon, etc.). Run `alembic upgrade head` to create the schema (currently head `0060`). **Back it up:** `bash scripts/backup_db.sh` (or register the daily task: `powershell -File scripts/install_backup_task.ps1`). **Restore:** `bash scripts/restore_db.sh backups/<file>.sql.gz`. ⚠️ Do **not** run the test suite (`REP_TEST_DSN`) against this DB — it TRUNCATEs every table; point `REP_TEST_DSN` at a disposable `*_test` database (the suite now refuses any non-`test` DSN). |
| **Auth secret** | `JWT_SECRET` | A long random string (e.g. `openssl rand -hex 32`). Signs login tokens. |
| **Vault encryption key** | `TOKEN_ENC_KEY` | **Required before connecting ANY external account.** Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. **Must differ from `JWT_SECRET`** (asserted at runtime). Store in a secrets manager, not the image. |
| **Public origin** | `PUBLIC_APP_ORIGIN` | The public URL of the console, e.g. `https://console.youragency.com` (no trailing slash). Used to build OAuth callback URLs **and** the public lead-magnet links. Local dev = `http://localhost:3000`. |
| **Admin seed** | `ADMIN_SEED_EMAIL`, `ADMIN_SEED_PASSWORD` | The first admin login created on boot. The super-admin (`logan@nexgenixai.com`) is the only one who can flip platform switches (billing, quota dashboard). |

---

## Tier 1 — Core intelligence (REQUIRED — this is what makes the product *do* anything)

Without these, audits/gap-analysis/content generation can't run.

### 1a. The LLM orchestrator (at least ONE required)
Drives gap analysis, content generation, compliance screening, answer scoring, the gap critic, fact-check.

| Provider | Env var | Notes |
|---|---|---|
| Anthropic (default) | `ANTHROPIC_API_KEY` | Recommended primary (`ORCHESTRATOR=anthropic`). |
| OpenAI | `OPENAI_API_KEY` | Alternative (`ORCHESTRATOR=openai`); also powers `gpt-image-1` visual generation. |

### 1b. AI answer engines (the audit checks what EACH says about the client)
Each engine joins the audit **only when its key is present** — absent engines aren't counted against coverage. For a meaningful "what AI says about you" audit you want **3–4** of these:

| Engine | Env var | Service |
|---|---|---|
| Anthropic / Claude | `ANTHROPIC_API_KEY` | (same key as 1a) |
| OpenAI / ChatGPT | `OPENAI_API_KEY` | (same key as 1a) |
| Perplexity | `PERPLEXITY_API_KEY` | perplexity.ai API |
| Google Gemini | `GEMINI_API_KEY` | Google AI Studio |
| Grok (xAI) | `XAI_API_KEY` (+ `XAI_BASE_URL`, `XAI_MODEL`) | Optional expansion engine |
| Bing Copilot | `BING_COPILOT_API_KEY` (+ base URL/model) | Optional, via an OpenAI-compatible proxy |

### 1c. Google SERP / local data — **Serper.dev** (effectively required for all SEO/local/review features)
`SERPER_API_KEY` (+ `SERPER_BASE_URL=https://google.serper.dev`). Powers: local-rank tracking,
Google AI-Overview capture, keyword-research grounding (related/PAA/autocomplete), **GBP review +
rating ingestion** (Serper Places/Reviews), and the mentions scan (web/news/social). **Paid**
(credits-based; ~$50/mo tiers). The single most-used external API after the LLMs.

---

## Tier 2 — Per-feature integrations (enable as needed)

Each row: what it powers · the third-party service (and whether it costs money) · the keys · **what
info you must collect from each client** · setup steps.

### 2a. Google Search Console — real organic clicks/impressions/ranking + indexing (Wave 1 / Wave 3)
- **Powers:** the Search-traffic page, ROI proof ("clicks earned by content we published"), the
  gap model's real-search grounding, and the white-hat indexing engine's index-status checks.
- **Service:** Google Cloud OAuth (free). **Cost: $0.**
- **Keys:** `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` (one shared client for GBP+GSC+GA).
- **Consent-screen scopes to add:** `webmasters.readonly` (+ `siteverification` for assisted
  onboarding).
- **Per-client info needed:** the client must have a **verified Search Console property** for their
  domain (URL-prefix `https://example.com/` or domain property `sc-domain:example.com`), and grant
  your OAuth app access by connecting in **Integrations → Connections → Google Search Console**,
  then pick the property. *History only exists from when the property was verified.*
- **Setup:** create the OAuth client in Google Cloud Console; set the authorized redirect URI to
  `{PUBLIC_APP_ORIGIN}/api/connections/google_search_console/callback`.

### 2b. Google Analytics (GA4) — sessions/conversions/behavior (Wave 1)
- **Powers:** the Behavior & conversions panel, content→conversion attribution, report ROI section.
- **Service:** same Google OAuth client. **Cost: $0.**
- **Scope to add:** `analytics.readonly`.
- **Per-client info needed:** a **GA4 property** with data, connected + property selected in the UI.
- **Setup:** redirect URI `{PUBLIC_APP_ORIGIN}/api/connections/google_analytics/callback`.

### 2c. Google Business Profile — review ingestion + review replies + local posts (Integrations P3/P5)
- **Powers:** importing the client's Google rating/reviews, drafting + (opt-in) posting review
  replies, GBP local posts.
- **Service:** Google OAuth, **scope `business.manage`**. **Cost: $0**, BUT the **review-reply API
  requires Google's allowlist approval** (apply via the Business Profile API access form) — until
  approved, connections show `gbp_access=pending` and replies stay draft-only.
- **Per-client info needed:** the client's Google account that **owns/manages the Business Profile**,
  connected via OAuth.
- **Setup:** redirect URI `{PUBLIC_APP_ORIGIN}/api/connections/google_business_profile/callback`;
  submit the GBP API access request for review-reply.

### 2d. WordPress — auto-publishing owned articles (Integrations P2)
- **Powers:** publishing approved content to the client's own WordPress site (the canonical owned
  channel) + the content-network/buffer-site option.
- **Service:** the client's own WordPress (self-hosted `.org` or `.com`). **Cost: $0** beyond their site.
- **Keys:** none global — credentials are entered per connection in the UI.
- **Per-client info needed:** the site URL (**HTTPS required**), a WordPress **username**, and an
  **Application Password** (WP Admin → Users → Profile → Application Passwords). Entered in
  **Integrations → Connections → WordPress**.

### 2e. Social publishing — **Ayrshare** (FB / IG / LinkedIn / Pinterest / X) (Integrations P5)
- **Powers:** posting approved social content + amplification across networks.
- **Service:** **Ayrshare** (ayrshare.com) — **PAID** (business plans; per-profile pricing). One
  business account; each client is a linked "profile."
- **Keys:** `AYRSHARE_API_KEY` (your account-level key).
- **Per-client info needed:** create an Ayrshare **user profile** per client and link their social
  accounts in Ayrshare; enter the client's **Profile-Key** in **Integrations → Connections →
  Social (Ayrshare)**.
- **Note:** X/Twitter posting has per-post cost on X's side; Reddit/Yelp are intentionally
  **draft-only** (never auto-posted).

### 2f. Transactional email — review requests, report delivery, lead follow-up (Wave 4 / GTM)
- **Powers:** sending review-request emails, emailing reports, (future) emailing the full report to
  captured leads.
- **Service:** any SMTP provider (defaults to **Zoho**; ZeptoMail/SendGrid/SES all work). **Cost:**
  free–cheap tiers exist.
- **Keys:** `SMTP_HOST`, `SMTP_PORT` (465 SSL / 587 STARTTLS), `SMTP_USER`, `SMTP_PASSWORD`,
  `EMAIL_FROM`. *Without these, emails are logged in dev mode, not sent (keyless-safe).*
- **Per-client info needed:** for review requests, a list of **client/customer emails** to send to.
- **SMS / GHL:** SMS sending and the GoHighLevel hook are **not wired** — the review-request
  templates are produced and an SMS/GHL sender can be added as a future connection. For now, review
  requests go out by email (or copy/paste the SMS template).

### 2g. Visual content — AI images / quote-cards / video briefs (LATER CI-4)
- **Powers:** generating images + branded quote-cards + short-video briefs for content.
- **Service / keys:** `IMAGE_PROVIDER` (`openai` | `stability` | `replicate`), `IMAGE_MODEL`
  (default `gpt-image-1`), `IMAGE_API_KEY` (blank = reuse `OPENAI_API_KEY`). Stability/Replicate use
  `STABILITY_API_KEY` / `REPLICATE_API_TOKEN`. Video: `VIDEO_PROVIDER`/`VIDEO_MODEL`/`VIDEO_API_KEY`
  (scaffold — a shootable brief is always produced; generative video runs only when set). **Quote-
  cards render locally with NO key.** **Cost:** per-image (OpenAI gpt-image-1 ≈ $0.01–0.17/image).
- **Per-client info needed:** none beyond the content brief. (For a regulated firm, AI imagery is
  auto-restricted to no real-person likenesses.)

### 2h. Keyword search-volume — real volume/difficulty/CPC (LATER CI-5)
- **Powers:** adds real monthly search volume + difficulty + CPC to keyword research and the
  equivalent-Ads-value estimate. *Without it, keyword research still works (Serper grounding), just
  without volume numbers.*
- **Service / keys:** `KEYWORD_VOLUME_PROVIDER` (`dataforseo` | `keywords_everywhere`) +
  `DATAFORSEO_LOGIN`/`DATAFORSEO_PASSWORD` **or** `KEYWORDS_EVERYWHERE_API_KEY`. **PAID** (both are
  cheap, usage-based).

### 2i. Crawler JS-rendering — **Firecrawl** (optional)
- **Powers:** rendering JS-heavy client sites during the site crawl (better on-page audit).
- **Keys:** `FIRECRAWL_API_KEY` (+ `FIRECRAWL_BASE`, `CRAWL_FIRECRAWL_MODE=auto`). **PAID** (optional;
  plain HTTP crawl works without it).

### 2j. Backlink profile (Wave 3, item 14)
- **Powers:** feeding a backlink report into the gap model + lost-link detection.
- **Service:** **no key required** — paste/upload an **Ahrefs/Semrush export** (or any backlink list)
  via the external-signals ingestion. A live Ahrefs/Semrush API is *not* wired (would be paid).

---

## Tier 3 — Optional / dormant (off by default)

| Feature | Env / setup | Notes |
|---|---|---|
| **Billing** (Stripe) | `STRIPE_SECRET_KEY` (+ webhook secret) | Fully built but **dormant** — the super-admin flips it on in Platform settings. Team Unstoppable (the pilot) stays unbilled. |
| **Auto-posting kill switch** | `AUTOPOST_GLOBAL_ENABLED=false` | Platform-wide master switch for ALL automated posting. Keep **false** until you're ready; even an opted-in client can't auto-post while it's off. |
| **Shared-platform quotas** | `PLATFORM_QUOTA_AYRSHARE_DAILY`, `PLATFORM_QUOTA_X_DAILY`, `PLATFORM_QUOTA_GBP_DAILY` | Account-level daily caps so a busy day can't blow a provider limit. Blank = unlimited. |
| **White-label report branding** | `REPORT_BRAND_NAME`, `REPORT_BRAND_LOGO`, `REPORT_BRAND_ACCENT` | Agency branding defaults; overridden per-business in **Account → White-label & sharing**. |
| **OAuth state secret** | `OAUTH_STATE_SECRET` | Optional; falls back to `JWT_SECRET`. |

---

## Per-client onboarding data (collected in the guided onboarding / Admin → Businesses)

This is the **information each client must provide** for the engine to produce good output:

- **Domain** (their website) — drives the site crawl, on-page audit, internal-linking, our-content attribution.
- **Services** (multi-tag) + **Industry** — drives keyword targeting + category-local prompts.
- **Areas served** (geo) — drives local rankings, GBP, category prompts.
- **Goal** (their positioning North-Star) — the score is "how close AI is to saying this."
- **Contested terms** — the negative frames to defend against (e.g. "scam", "MLM").
- **Firm type** (`ria` | `broker_dealer` | `insurance` | `non_financial`) — sets the correct
  compliance rules + restricts AI imagery of real people for regulated firms.
- **Competitors** — for AI share-of-voice benchmarking + "questions rivals win."
- **Monitor keywords** — for the mentions scan (add each variant separately).
- **NAP** (Name / Address / Phone) — for review requests, directory citations, local consistency.

### Per-integration grants the client must perform (one-time, via the Connections UI)
1. **Google Search Console** — verify a property + connect (OAuth) + pick it.
2. **Google Analytics** — connect (OAuth) + pick the GA4 property.
3. **Google Business Profile** — connect the Google account that manages the profile.
4. **WordPress** — provide site URL + username + an Application Password.
5. **Social (Ayrshare)** — link their social accounts in Ayrshare; provide the Profile-Key.

---

## "What works with nothing configured?"

Even with **only Tier 0 + an LLM key + Serper**, you get: the AI-reputation audit, gap analysis,
content generation (drafts), keyword research, local-rank tracking, mentions, the report, and all
the read dashboards. Everything else degrades gracefully:
- No GSC/GA → the Search-traffic pages show a "connect" hint; the gap model just doesn't use search outcomes.
- No publishing connections → content is generated + approved; you publish manually.
- No email → review requests + reports are produced but logged, not sent.
- No image key → quote-cards still render locally; AI images skip.
- No volume key → keyword research runs without volume numbers.

So you can demo and sell on Tier 1 alone, then turn on per-client integrations as you onboard them.

---

## Cost summary (rough)

| Required | Approx. monthly |
|---|---|
| Postgres (managed) | $0–25 |
| LLM (Anthropic/OpenAI) | usage-based; ~$7–12 per full audit+content cycle |
| Answer engines (Perplexity/Gemini) | usage-based, small |
| Serper.dev | ~$50+ (credits) |
| **Optional / paid when enabled** | |
| Ayrshare (social) | paid plan (per profiles) |
| DataForSEO / Keywords Everywhere | cheap, usage-based |
| Firecrawl | optional paid |
| SMTP (Zoho/SendGrid) | free–cheap |
| Image generation | ~$0.01–0.17/image |
| Google GSC/GA/GBP OAuth | **$0** (GBP review-reply needs free allowlist approval) |
