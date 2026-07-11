"use client";

// Data sources status — one honest surface showing what's connected vs. dormant, so features never
// sit silently empty. OAuth sources (GSC/GA4) show connected + last sync; env-key features
// (PageSpeed, keyword volume) show configured / needs-a-key with exactly which key to set and what
// it unlocks. Live-wired to /data-sources. `compact` renders a one-line strip for embedding.

import { useDataSources } from "@/lib/hooks";
import type { DataSources, DataSourceStatus } from "@/lib/types";

type Row = { key: keyof DataSources; label: string; kind: "oauth" | "key" };
const ROWS: Row[] = [
  { key: "google_search_console", label: "Search Console", kind: "oauth" },
  { key: "google_analytics", label: "Google Analytics (GA4)", kind: "oauth" },
  { key: "pagespeed", label: "PageSpeed / Core Web Vitals", kind: "key" },
  { key: "keyword_volume", label: "Keyword volume", kind: "key" },
];

function isReady(s: DataSourceStatus, kind: "oauth" | "key"): boolean {
  return kind === "oauth" ? !!s.connected : !!s.configured;
}

function agoLabel(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return "";
  const h = Math.max(0, Math.round((Date.now() - d) / 3.6e6));
  return h < 1 ? "just now" : h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
}

export function DataSourcesPanel({ businessId, compact = false }: { businessId: number | null; compact?: boolean }) {
  const { data } = useDataSources(businessId);
  if (!data) return null;
  const rows = ROWS.map((r) => ({ ...r, s: data[r.key], ready: isReady(data[r.key], r.kind) }));
  const readyCount = rows.filter((r) => r.ready).length;

  if (compact) {
    return (
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-[12px] border border-line bg-card px-3.5 py-2.5">
        <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-ink-4">Data sources {readyCount}/{rows.length}</span>
        {rows.map((r) => (
          <span key={r.key} className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-2" title={r.s.unlocks}>
            <span className="h-2 w-2 rounded-full" style={{ background: r.ready ? "#0f9d63" : "#c9b24f" }} />
            {r.label.replace(" / Core Web Vitals", "").replace(" (GA4)", "")}
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className="rounded-[14px] border border-line bg-card p-4 shadow-[0_1px_2px_rgba(20,24,31,0.05)]">
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <h3 className="text-base font-semibold tracking-tight text-slate-900">Data sources</h3>
        <span className="font-mono text-[12px] text-ink-4">{readyCount}/{rows.length} active</span>
      </div>
      <p className="mb-3 text-xs text-slate-500">Connect these to light up the new analysis. Each row shows what it unlocks; anything not yet active is why a card might be empty.</p>
      <div className="divide-y divide-line">
        {rows.map((r) => (
          <div key={r.key} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: r.ready ? "#0f9d63" : "#c9b24f" }} />
                <span className="text-[14px] font-semibold text-ink">{r.label}</span>
                {r.ready && r.kind === "oauth" && r.s.synced_at ? <span className="font-mono text-[11px] text-ink-4">synced {agoLabel(r.s.synced_at)}</span> : null}
              </div>
              <div className="ml-[18px] text-[12.5px] text-ink-3">{r.s.unlocks}</div>
            </div>
            <div className="shrink-0 text-right">
              {r.ready ? (
                <span className="rounded-full bg-good-bg px-2.5 py-1 font-mono text-[11px] font-semibold text-good">{r.kind === "oauth" ? "Connected" : "Configured"}</span>
              ) : r.kind === "oauth" ? (
                <span className="rounded-full bg-amber-50 px-2.5 py-1 font-mono text-[11px] font-semibold text-amber-700">Connect below ↓</span>
              ) : (
                <span className="rounded-full bg-amber-50 px-2.5 py-1 font-mono text-[11px] font-semibold text-amber-700" title={`Set ${r.s.env_key} in your environment`}>Set {r.s.env_key?.split(" ")[0]}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
