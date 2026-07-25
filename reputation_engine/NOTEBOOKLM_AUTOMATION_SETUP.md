# NotebookLM audio auto-download — owner setup

Google's NotebookLM has **no API to download** a finished Audio Overview — only the Studio web UI can.
To auto-land the podcast in Media (instead of the manual "Open in NotebookLM" link), the platform
drives that UI with Playwright. This is **dormant until you provision the pieces below**, because
automating NotebookLM login violates Google's ToS and needs a real logged-in session.

## Why the guardrails
- **Dedicated, isolated Google account.** Automating login can get an account **suspended**. Use a
  throwaway Google/Workspace account that owns **only** the Team Unstoppable notebook — never your
  primary account. That contains the blast radius.
- **Never run it on the Railway worker.** Railway's datacenter IP is flagged by Google, and Chromium
  would OOM the worker. Use a dedicated stable-IP host or a managed remote browser.
- **Human-gated.** NotebookLM audio is AI-generated (two hosts, non-verbatim), so every downloaded
  episode still lands as `pending_review` and is compliance-screened before anything is published.

## One-time setup
1. **Create the dedicated Google account** and share/move the Team Unstoppable notebook to it (or
   generate podcasts under it so it owns the notebook). Confirm it can open NotebookLM Studio and play
   the audio in a normal browser.
2. **Pick where the browser runs** (either):
   - **Managed remote browser** (recommended): a Browserbase / browserless instance with a stable IP.
     You get a `ws://…` CDP endpoint → set `NOTEBOOKLM_BROWSER_CDP`.
   - **A small dedicated VM / your own machine** with Playwright + Chromium installed
     (`pip install playwright && playwright install chromium`). No CDP endpoint needed there.
3. **Capture the session once (human login):** in a real headed browser on that host, log into the
   dedicated Google account, open NotebookLM, then export the Playwright `storageState` JSON (cookies +
   localStorage). Store it either as a file (set `NOTEBOOKLM_BROWSER_STATE=/path/to/state.json`) or in
   the connections vault (`NOTEBOOKLM_BROWSER_STATE=vault:<key>`).
4. **Validate the Studio selectors live, then flip the switch.** The Studio DOM changes often, so the
   selectors in `notebooklm_browser.py` need a quick live check against the current UI (I do this with
   you in one session, driving the real notebook). Only after that passes do you set
   `NOTEBOOKLM_BROWSER_READY=1`. Until then the job returns `{skipped}` and nothing runs.

## Env summary (set on the browser host / worker that triggers it)
| Var | Purpose |
|---|---|
| `NOTEBOOKLM_BROWSER_READY` | `1` only AFTER selectors are validated live. The master gate. |
| `NOTEBOOKLM_BROWSER_STATE` | Path to (or `vault:<key>` of) the captured storageState JSON. |
| `NOTEBOOKLM_BROWSER_CDP` | (optional) `ws://…` CDP endpoint of a managed remote browser. |
| `NOTEBOOKLM_PERSIST` | `1` (default) reuses one notebook per business; `0` = old behavior. |

## Ongoing
- The scraped session **has no refresh token** — Google invalidates it on new-device/location/password
  events and periodically. When the job returns `login_required`, re-capture the storageState (step 3).
  Keeping a stable IP + warm session makes this rare.
- Trigger: a `notebooklm_render` job (per podcast draft). Once `READY`, I'll wire the "Download to
  Media" button on the podcast card + optionally auto-enqueue it after a podcast generates.

## What's already built (dormant, waiting on the above)
- `notebooklm_browser.py` — the Playwright fetch (open notebook → find the just-created audio card →
  download only that file), fully gated behind `configured()`.
- `rich_media_generator.notebooklm_download_audio()` + `ingest_notebook_audio()` — store the audio
  durably and attach it to the draft's `audio_url` so the Media modal plays it in-app (idempotent).
- `notebooklm_render` job (fail-loud: a skipped/failed download marks the job failed, never a false
  "complete").
- The persistent notebook itself is **already live** — podcasts now reuse one Team Unstoppable
  notebook instead of creating a new one each time.
