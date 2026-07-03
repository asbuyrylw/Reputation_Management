"use client";

import Link from "next/link";
import { useConnections, useGscSummary } from "@/lib/hooks";

// Rec 6 — connection precondition banner, shown BEFORE the owner spends on a run. An audit still
// runs without integrations, but two things make each run (and the credits it costs) worth far more:
//  1. Google Search Console → real click/rank data feeds the score, gaps and projections.
//  2. A publishing channel (WordPress / social / GBP) → approved content actually posts, so the
//     "approve → publish → crowd out the negative" value loop can close instead of dead-ending.
// This nudges (never blocks): it only renders when something material is missing, and links to the
// one place to fix it. Self-hides once both are connected.
const PUBLISH_KINDS = new Set(["wordpress_org", "google_business_profile", "ayrshare_profile", "zernia"]);

export function PipelinePrecheckBanner({ businessId }: { businessId: number | null }) {
  const { data: conns } = useConnections(businessId);
  const { data: gsc } = useGscSummary(businessId);

  // Treat "collecting" or real data as connected even if the connection row isn't surfaced here.
  const active = (conns?.connections ?? []).filter((c) => c.status === "active");
  const gscConnected = !!(gsc?.has_data || gsc?.collecting) || active.some((c) => c.kind === "google_search_console");
  const publishConnected = active.some((c) => PUBLISH_KINDS.has(c.kind));

  // Wait for at least one data source before deciding (avoids a flash before queries resolve).
  if (conns === undefined && gsc === undefined) return null;
  if (gscConnected && publishConnected) return null;

  const missing: { label: string; why: string }[] = [];
  if (!gscConnected) missing.push({ label: "Google Search Console", why: "real Google clicks & rankings sharpen your score, gaps and projections" });
  if (!publishConnected) missing.push({ label: "a publishing channel", why: "approved content posts automatically instead of waiting on a manual copy-paste" });

  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
      <div className="min-w-[240px] flex-1 text-sm text-amber-900">
        <span className="font-semibold">Get more from every run.</span>{" "}
        Connect {missing.map((m, i) => (
          <span key={m.label}>
            {i > 0 ? (i === missing.length - 1 ? " and " : ", ") : ""}
            <span className="font-medium">{m.label}</span>
          </span>
        ))}{" "}
        so {missing.map((m) => m.why).join("; ")}.
      </div>
      <Link
        href="/integrations"
        className="shrink-0 rounded-[10px] border border-amber-300 bg-white px-3.5 py-2 text-[13px] font-semibold text-amber-900 hover:bg-amber-100"
      >
        Connect →
      </Link>
    </div>
  );
}
