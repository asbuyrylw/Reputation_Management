// Runs on Yelp/Reddit/Facebook pages. Shows the reply Koob already drafted for whatever
// review/comment the operator is looking at, in a small floating panel -- the operator still
// reviews it and clicks "post" themselves on the platform's own page, so nothing here automates
// posting or violates any platform's terms of service.

(function () {
  const HOST_SOURCE = [
    { test: /(^|\.)yelp\.com$/, source: "yelp" },
    { test: /(^|\.)reddit\.com$/, source: "reddit" },
    { test: /(^|\.)facebook\.com$/, source: "facebook" },
  ];

  function currentSource() {
    const host = location.hostname;
    const match = HOST_SOURCE.find((h) => h.test.test(host));
    return match ? match.source : null;
  }

  function fetchQueue() {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({ type: "FETCH_QUEUE" }, (res) => resolve(res || { ok: false, error: "no_response" }));
    });
  }

  // Best-effort: does this item look like it's about the page we're currently on? A loose match
  // (shared URL path segment) beats requiring an exact URL, since platforms rewrite/redirect
  // review and comment permalinks often.
  function relevance(item) {
    if (!item.url) return 0;
    try {
      const itemUrl = new URL(item.url);
      if (itemUrl.hostname !== location.hostname) return 0;
      if (location.href.includes(itemUrl.pathname) || itemUrl.pathname === location.pathname) return 2;
      return 1; // same platform, different page -- still worth surfacing
    } catch {
      return 0;
    }
  }

  function buildPanel(items) {
    const existing = document.getElementById("koob-reply-assist-panel");
    if (existing) existing.remove();

    const panel = document.createElement("div");
    panel.id = "koob-reply-assist-panel";

    const header = document.createElement("div");
    header.className = "koob-ra-header";
    header.innerHTML = `<span>Koob Reply Assist</span>`;
    const close = document.createElement("button");
    close.textContent = "×";
    close.className = "koob-ra-close";
    close.onclick = () => panel.remove();
    header.appendChild(close);
    panel.appendChild(header);

    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "koob-ra-empty";
      empty.textContent = "No pending drafted replies for this platform right now.";
      panel.appendChild(empty);
    } else {
      const list = document.createElement("div");
      list.className = "koob-ra-list";
      for (const item of items) {
        const row = document.createElement("div");
        row.className = "koob-ra-item";
        const title = document.createElement("div");
        title.className = "koob-ra-title";
        title.textContent = item.title || "(untitled)";
        const draft = document.createElement("div");
        draft.className = "koob-ra-draft";
        draft.textContent = item.draft;
        const actions = document.createElement("div");
        actions.className = "koob-ra-actions";
        const copyBtn = document.createElement("button");
        copyBtn.textContent = "Copy reply";
        copyBtn.onclick = () => {
          navigator.clipboard.writeText(item.draft).then(() => {
            copyBtn.textContent = "Copied!";
            setTimeout(() => (copyBtn.textContent = "Copy reply"), 1500);
          });
        };
        const insertBtn = document.createElement("button");
        insertBtn.textContent = "Insert into focused box";
        insertBtn.title = "Pastes into whichever text box on the page currently has focus.";
        insertBtn.onclick = () => insertIntoFocused(item.draft);
        actions.appendChild(copyBtn);
        actions.appendChild(insertBtn);
        row.appendChild(title);
        row.appendChild(draft);
        row.appendChild(actions);
        list.appendChild(row);
      }
      panel.appendChild(list);
    }

    document.body.appendChild(panel);
  }

  function insertIntoFocused(text) {
    const el = document.activeElement;
    if (!el) return;
    if (el.tagName === "TEXTAREA" || (el.tagName === "INPUT" && el.type === "text")) {
      const start = el.selectionStart ?? el.value.length;
      const end = el.selectionEnd ?? el.value.length;
      el.value = el.value.slice(0, start) + text + el.value.slice(end);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      return;
    }
    if (el.isContentEditable) {
      document.execCommand("insertText", false, text);
      return;
    }
    // No focused editable box -- fall back to clipboard so the operator can paste manually.
    navigator.clipboard.writeText(text);
  }

  async function run() {
    const source = currentSource();
    if (!source) return;
    const res = await fetchQueue();
    if (!res.ok) {
      if (res.error === "not_configured") return; // silent until the operator sets up options
      return;
    }
    const items = (res.items || [])
      .filter((i) => (i.source || "").toLowerCase() === source)
      .map((i) => ({ ...i, _rel: relevance(i) }))
      .sort((a, b) => b._rel - a._rel);
    if (items.length) buildPanel(items);
  }

  // Run once the page settles, and again if the operator navigates within an SPA (Reddit/Yelp/
  // Facebook are all client-routed) by watching for URL changes.
  let lastHref = location.href;
  setInterval(() => {
    if (location.href !== lastHref) {
      lastHref = location.href;
      run();
    }
  }, 1500);
  run();
})();
