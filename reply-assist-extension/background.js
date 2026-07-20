// Background service worker. Runs the actual network fetch to the Koob API -- a privileged
// extension context whose requests aren't subject to page-level CORS the way a content script's
// would be, as long as the target origin is in optional_host_permissions and has been granted.
// The content script never talks to the API directly; it only messages this worker.

async function fetchQueue() {
  const { apiBase, extToken } = await chrome.storage.sync.get(["apiBase", "extToken"]);
  if (!apiBase || !extToken) {
    return { ok: false, error: "not_configured" };
  }
  try {
    const res = await fetch(`${apiBase.replace(/\/$/, "")}/ext/v1/queue`, {
      headers: { Authorization: `Bearer ${extToken}` },
    });
    if (!res.ok) {
      return { ok: false, error: `http_${res.status}` };
    }
    const data = await res.json();
    return { ok: true, items: data.items || [] };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "FETCH_QUEUE") {
    fetchQueue().then(sendResponse);
    return true; // keep the message channel open for the async response
  }
  return false;
});
