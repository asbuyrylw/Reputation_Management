// Credentialed CSV/file download helper. Reuses the same API base + cookie-based auth the
// fetch client uses (the httpOnly `rc_token` session cookie is sent via credentials:"include"),
// fetches the endpoint as a Blob, and triggers a browser download via a temporary <a download>.
// GET-only endpoints (exports) need no CSRF token.

import { apiBase, ApiError } from "./api";

export async function downloadCsv(path: string, filename: string): Promise<void> {
  const res = await fetch(`${apiBase()}${path}`, { credentials: "include" });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const blob = await res.blob();
  triggerDownload(blob, filename);
}

// Download an in-memory string as a file (e.g. a generated llms.txt we already hold). No
// network call — the content is already on the client — so this works offline and needs no auth.
export function downloadText(content: string, filename: string, mime = "text/plain"): void {
  triggerDownload(new Blob([content], { type: mime }), filename);
}

// Shared blob -> browser-download trigger via a temporary <a download>.
function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
