// Typed fetch client. Auth is cookie-based: the httpOnly `rc_token` session cookie is
// sent automatically (credentials: "include"); writes echo the readable `csrf_token`
// cookie in the X-CSRF-Token header (double-submit CSRF). No token is stored in JS.

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

// A billing/quota wall: 402 (subscription inactive/trial ended) or 429 (over the plan's
// monthly limit). The UI turns these into an upgrade prompt instead of a generic red error.
export function isBillingError(err: unknown): err is ApiError {
  return err instanceof ApiError && (err.status === 402 || err.status === 429);
}

export interface FetchOpts {
  method?: string;
  body?: unknown;
}

function csrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export async function apiFetch<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  const method = opts.method || "GET";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (method !== "GET") {
    const t = csrfToken();
    if (t) headers["X-CSRF-Token"] = t;
  }
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    credentials: "include",
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      if (j?.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// Credentialed binary download (e.g. a .docx report): fetch as a blob with the session
// cookie, then trigger a browser download. GET-only, so no CSRF token is needed.
export async function apiDownload(path: string, filename: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { credentials: "include" });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
