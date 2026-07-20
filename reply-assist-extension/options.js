const $apiBase = document.getElementById("apiBase");
const $token = document.getElementById("extToken");
const $status = document.getElementById("status");
const $save = document.getElementById("save");

chrome.storage.sync.get(["apiBase", "extToken"], (v) => {
  if (v.apiBase) $apiBase.value = v.apiBase;
  if (v.extToken) $token.value = v.extToken;
});

function setStatus(text, ok) {
  $status.textContent = text;
  $status.className = ok ? "ok" : "err";
}

$save.addEventListener("click", async () => {
  const apiBase = $apiBase.value.trim().replace(/\/$/, "");
  const extToken = $token.value.trim();
  if (!apiBase || !extToken) {
    setStatus("Both fields are required.", false);
    return;
  }
  let origin;
  try {
    origin = new URL(apiBase).origin + "/*";
  } catch {
    setStatus("That doesn't look like a valid URL.", false);
    return;
  }

  $save.disabled = true;
  try {
    // Request permission to talk to this origin from the background worker -- the runtime
    // (not manifest-time) grant is how an MV3 extension supports a user-supplied API host it
    // can't know in advance.
    const granted = await chrome.permissions.request({ origins: [origin] });
    if (!granted) {
      setStatus("Permission to reach that URL was not granted.", false);
      return;
    }
    await chrome.storage.sync.set({ apiBase, extToken });
    setStatus("Saved. Open a Yelp, Reddit, or Facebook page to see it work.", true);
  } finally {
    $save.disabled = false;
  }
});
