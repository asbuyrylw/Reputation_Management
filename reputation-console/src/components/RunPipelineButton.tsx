"use client";

import { useState } from "react";
import { useRunEverything } from "@/lib/hooks";
import { isBillingError } from "@/lib/api";
import { UpgradeModal } from "@/components/UpgradeModal";

// Owner-safe "run/refresh everything" control. Wraps the run-everything endpoint (which is gated on
// `require_business_editor`, NOT admin) so an OWNER can refresh their whole picture — audit, crawl,
// gaps, plan, citations, rankings, mentions, content & report — from the dashboard, without ever
// touching the admin Jobs page. A confirm step guards the ~$8-12 spend; a billing wall (402/429)
// becomes an upgrade prompt; the once-a-day server rate limit surfaces as a plain message.
export function RunPipelineButton({
  businessId,
  label = "Refresh data",
  className = "",
  variant = "primary",
}: {
  businessId: number | null;
  label?: string;
  className?: string;
  variant?: "primary" | "secondary";
}) {
  const runAll = useRunEverything(businessId);
  const [confirm, setConfirm] = useState(false);
  const [upgrade, setUpgrade] = useState<string | null>(null);

  const base =
    variant === "primary"
      ? "bg-indigo text-white hover:bg-indigo-strong"
      : "border border-line-2 bg-white text-ink-2 hover:bg-line/60";

  const go = () =>
    runAll.mutate(undefined, {
      onSuccess: () => setConfirm(false),
      onError: (e) => { if (isBillingError(e)) { setUpgrade((e as Error).message); setConfirm(false); } },
    });
  const showGenericError = runAll.isError && !isBillingError(runAll.error);

  return (
    <span className="inline-flex flex-col items-end gap-1">
      {!confirm ? (
        <button
          type="button"
          disabled={!businessId || runAll.isPending}
          // Always route through the spend confirm — never fire go() directly. (A stale isSuccess
          // must not let a click, e.g. after switching businesses, start an unconfirmed ~$8-12 run.)
          onClick={() => setConfirm(true)}
          title="Re-run the full pipeline for the latest picture (uses API credits; once per day)"
          className={`inline-flex items-center gap-2 rounded-[10px] px-3.5 py-2 text-[13px] font-semibold transition disabled:opacity-50 ${base} ${className}`}
        >
          {runAll.isPending && (
            <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden>
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
          )}
          <span aria-hidden>↻</span> {runAll.isPending ? "Starting…" : runAll.isSuccess ? "Refreshing — run again" : label}
        </button>
      ) : (
        <span className="inline-flex items-center gap-2 rounded-[10px] border border-indigo-100 bg-indigo-050 px-3 py-1.5 text-[12.5px] text-ink-2">
          Runs the full pipeline (uses API credits).
          <button onClick={go} className="rounded-md bg-indigo px-2.5 py-1 text-xs font-semibold text-white hover:bg-indigo-strong">Run it</button>
          <button onClick={() => setConfirm(false)} className="rounded-md border border-line-2 px-2.5 py-1 text-xs font-semibold text-ink-2 hover:bg-line/60">Cancel</button>
        </span>
      )}
      {showGenericError && <span className="text-xs text-alert">{(runAll.error as Error)?.message ?? "Couldn’t start — try again."}</span>}
      {runAll.isSuccess && !confirm && <span className="text-xs text-good">Queued — track it above.</span>}
      {upgrade && <UpgradeModal message={upgrade} onClose={() => setUpgrade(null)} />}
    </span>
  );
}
