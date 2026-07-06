# Koob Reply Assist (Chrome extension)

Closes one specific gap: Yelp, Reddit, and Facebook comment replies can't be auto-posted from the
console (those platforms' terms forbid automated posting, and Yelp/Reddit don't offer a reply API
anyway). This extension shows the reply Koob already drafted right on the page you're looking at,
so you review it and paste it in — you still click "post" yourself, so nothing here automates
posting or touches anyone's terms of service.

## Install (unpacked, until this is published to the Chrome Web Store)

1. Open `chrome://extensions`, turn on **Developer mode** (top right).
2. Click **Load unpacked**, select this `reply-assist-extension/` folder.
3. Click the extension's icon (or right-click → Options) to open settings.

## Set up

1. In the console, go to **Integrations → Reply Assist extension** and click **+ New token**.
   Copy the token immediately — it's shown once and can't be retrieved again (revoke and issue a
   new one if you lose it).
2. In the extension's options page, paste your API base URL (e.g. `https://api.yourdomain.com`)
   and the token, then **Save**. Chrome will ask you to confirm access to that URL — approve it;
   that's what lets the extension's background worker read the pending-reply queue.
3. Visit a Yelp business page, a Reddit thread, or a Facebook page with a pending reply — a small
   panel appears bottom-right with the drafted text, a **Copy reply** button, and an
   **Insert into focused box** button that pastes into whatever text field currently has focus on
   the page.

## How it works

- `background.js` is the only place that talks to the API — a privileged extension context, so its
  fetches aren't blocked by page-level CORS the way a content script's would be, as long as the
  target origin was granted via `chrome.permissions.request` in the options page.
- `content.js` runs on Yelp/Reddit/Facebook pages, asks the background worker for the queue, filters
  to the current platform, and renders the panel. It re-checks on URL changes since all three sites
  are client-routed SPAs.
- The API endpoint (`GET /ext/v1/queue`) is read-only and bearer-token-scoped to one business —
  see `rep_engine/api/routers/ext_router.py` and `rep_engine/ext_tokens.py` in the main repo.

## Limitations (by design)

- No auto-posting, ever — this is a copy/paste aid, not automation.
- "Insert into focused box" is a best-effort DOM interaction (works for a focused `<textarea>`,
  text `<input>`, or `contenteditable`); if none is focused it falls back to clipboard copy.
- Matching a drafted reply to the exact review/comment you're viewing is heuristic (URL overlap) —
  when in doubt it shows all pending items for that platform rather than hiding one that might be
  relevant.
