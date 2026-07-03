"use client";

// PUBLIC lead-magnet page — lives at the app ROOT (not under (console)), so it has NO auth,
// no sidebar, no console chrome. A prospect reaches it through a shared link. It fetches the
// sanitized public summary with a raw same-origin fetch ("/api/public/audit/{token}") — no
// auth headers, because the visitor isn't logged in — and shows a branded teaser + an
// email-capture form. The FULL report is emailed only after they leave an email (honest copy).

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import type { PublicAudit } from "@/lib/types";

// Fallback accent if the business hasn't set a brand color.
const DEFAULT_ACCENT = "#4f46e5"; // indigo-600

// A simple hex sanity check so a bad value can't break inline styles.
function safeAccent(hex: string | null | undefined): string {
  if (hex && /^#[0-9a-fA-F]{3,8}$/.test(hex)) return hex;
  return DEFAULT_ACCENT;
}

// Big circular score ring drawn with conic-gradient (no chart dep). score is 0..100.
function ScoreRing({ score, accent }: { score: number; accent: string }) {
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div
      className="relative grid h-40 w-40 place-items-center rounded-full"
      style={{ background: `conic-gradient(${accent} ${pct * 3.6}deg, rgb(226 232 240) 0deg)` }}
      role="img"
      aria-label={`AI reputation score ${pct} out of 100`}
    >
      <div className="grid h-32 w-32 place-items-center rounded-full bg-white shadow-inner">
        <div className="text-center leading-none">
          <span className="text-4xl font-bold tracking-tight" style={{ color: accent }}>
            {pct}
          </span>
          <span className="text-lg font-semibold text-slate-400">/100</span>
        </div>
      </div>
    </div>
  );
}

export default function PublicAuditPage() {
  const params = useParams<{ token: string }>();
  const token = params?.token;

  const [data, setData] = useState<PublicAudit | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "notfound" | "error">("loading");

  // lead-capture form state
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    setState("loading");
    fetch(`/api/public/audit/${encodeURIComponent(token)}`)
      .then(async (res) => {
        if (res.status === 404) {
          if (alive) setState("notfound");
          return;
        }
        if (!res.ok) throw new Error(String(res.status));
        const json = (await res.json()) as PublicAudit;
        if (!alive) return;
        if (!json.found) {
          setState("notfound");
          return;
        }
        setData(json);
        setState("ready");
      })
      .catch(() => {
        if (alive) setState("error");
      });
    return () => {
      alive = false;
    };
  }, [token]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const res = await fetch(`/api/public/audit/${encodeURIComponent(token)}/lead`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, name: name || undefined }),
      });
      if (res.status === 400) {
        setFormError("Please enter a valid email address.");
        return;
      }
      if (!res.ok) throw new Error(String(res.status));
      setSubmitted(true);
    } catch {
      setFormError("Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  // ---- shells (no console chrome) ----
  if (state === "loading") {
    return (
      <Shell>
        <div className="flex items-center justify-center p-10">
          <div className="h-7 w-7 animate-spin rounded-full border-[3px] border-indigo-200 border-t-indigo-600" />
        </div>
      </Shell>
    );
  }

  if (state === "notfound") {
    return (
      <Shell>
        <div className="rounded-2xl bg-white p-8 text-center shadow-xl ring-1 ring-slate-900/[0.06]">
          <h1 className="text-xl font-semibold text-slate-900">This link isn’t valid</h1>
          <p className="mt-2 text-sm text-slate-500">
            The audit link you followed has expired or doesn’t exist. Ask whoever shared it for an updated link.
          </p>
        </div>
      </Shell>
    );
  }

  if (state === "error" || !data) {
    return (
      <Shell>
        <div className="rounded-2xl bg-white p-8 text-center shadow-xl ring-1 ring-slate-900/[0.06]">
          <h1 className="text-xl font-semibold text-slate-900">We couldn’t load this report</h1>
          <p className="mt-2 text-sm text-slate-500">Please refresh the page in a moment.</p>
        </div>
      </Shell>
    );
  }

  const accent = safeAccent(data.branding.accent);
  const brandName = data.branding.brand_name || "AI Reputation Report";
  const hasScore = data.has_audit && data.score != null;
  const gaps = (data.top_gaps || []).slice(0, 3);

  return (
    <Shell accent={accent}>
      <div className="overflow-hidden rounded-2xl bg-white shadow-xl ring-1 ring-slate-900/[0.06]">
        {/* branded header */}
        <div className="flex items-center gap-3 border-b border-slate-100 px-6 py-5">
          {data.branding.logo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={data.branding.logo_url}
              alt={brandName}
              className="h-9 w-auto max-w-[160px] object-contain"
            />
          ) : (
            <span
              className="grid h-9 w-9 place-items-center rounded-lg text-sm font-bold text-white"
              style={{ backgroundColor: accent }}
              aria-hidden
            >
              {brandName.charAt(0).toUpperCase()}
            </span>
          )}
          <span className="text-sm font-semibold text-slate-700">{brandName}</span>
        </div>

        <div className="px-6 py-8 sm:px-8">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em]" style={{ color: accent }}>
            AI Reputation Snapshot
          </div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            {data.business}
          </h1>
          {data.area && <p className="mt-1 text-sm text-slate-500">{data.area}</p>}

          {/* score */}
          <div className="mt-7 flex flex-col items-center gap-5 sm:flex-row sm:items-center sm:gap-7">
            {hasScore ? (
              <ScoreRing score={data.score as number} accent={accent} />
            ) : (
              <div className="grid h-40 w-40 place-items-center rounded-full bg-slate-50 text-center ring-1 ring-slate-200">
                <span className="px-4 text-xs font-medium text-slate-400">
                  Score pending — request the full report below
                </span>
              </div>
            )}
            <div className="flex-1 text-center sm:text-left">
              {data.band && (
                <span
                  className="inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold"
                  style={{ backgroundColor: `${accent}1a`, color: accent }}
                >
                  {data.band}
                </span>
              )}
              {data.teaser && (
                <p className="mt-3 text-[15px] leading-relaxed text-slate-600">{data.teaser}</p>
              )}
            </div>
          </div>

          {/* teased gaps */}
          {gaps.length > 0 && (
            <div className="mt-8">
              <h2 className="text-sm font-semibold text-slate-900">What AI gets wrong about you</h2>
              <ul className="mt-3 space-y-2.5">
                {gaps.map((gap, i) => (
                  <li key={i} className="flex items-start gap-3 rounded-xl bg-slate-50 px-4 py-3">
                    <span
                      className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full text-[11px] font-bold text-white"
                      style={{ backgroundColor: accent }}
                      aria-hidden
                    >
                      {i + 1}
                    </span>
                    <span className="text-sm leading-relaxed text-slate-700">{gap}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* email capture / thank-you */}
          <div className="mt-8 rounded-2xl border border-slate-200 bg-slate-50/70 p-5 sm:p-6">
            {submitted ? (
              <div className="text-center">
                <div
                  className="mx-auto grid h-12 w-12 place-items-center rounded-full text-white"
                  style={{ backgroundColor: accent }}
                  aria-hidden
                >
                  <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6" stroke="currentColor" strokeWidth={2.5}>
                    <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <h2 className="mt-3 text-base font-semibold text-slate-900">Check your inbox</h2>
                <p className="mt-1 text-sm text-slate-500">
                  We’ll send the full breakdown — every gap, every source, and exactly what to fix first.
                </p>
              </div>
            ) : (
              <>
                <h2 className="text-base font-semibold text-slate-900">Get the full breakdown</h2>
                <p className="mt-1 text-sm text-slate-500">
                  This is just a snapshot. Enter your email and we’ll send the complete report — the specific
                  prompts, sources, and the fastest fixes.
                </p>
                <form onSubmit={onSubmit} className="mt-4 space-y-3">
                  <div>
                    <label className="sr-only" htmlFor="lead-email">Email</label>
                    <input
                      id="lead-email"
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@company.com"
                      autoComplete="email"
                      className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm focus:border-slate-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="sr-only" htmlFor="lead-name">Name (optional)</label>
                    <input
                      id="lead-name"
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Your name (optional)"
                      autoComplete="name"
                      className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm focus:border-slate-500 focus:outline-none"
                    />
                  </div>
                  {formError && <p className="text-sm text-rose-600">{formError}</p>}
                  <button
                    type="submit"
                    disabled={submitting}
                    className="w-full rounded-lg px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-opacity hover:opacity-90 disabled:opacity-50"
                    style={{ backgroundColor: accent }}
                  >
                    {submitting ? "Sending…" : "Send me the full report"}
                  </button>
                  <p className="text-center text-xs text-slate-400">No spam. Unsubscribe anytime.</p>
                </form>
              </>
            )}
          </div>
        </div>
      </div>

      <p className="mt-5 text-center text-xs text-slate-400">
        Powered by <span className="font-medium text-slate-500">{brandName}</span>
      </p>
    </Shell>
  );
}

// Centered card on a soft background. `accent` softly tints the page glow.
function Shell({ children, accent }: { children: React.ReactNode; accent?: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-linear-to-b from-slate-50 to-slate-100 p-4">
      <div
        className="w-full max-w-lg"
        style={accent ? { ["--page-accent" as string]: accent } : undefined}
      >
        {children}
      </div>
    </div>
  );
}
