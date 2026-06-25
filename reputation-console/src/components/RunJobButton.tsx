"use client";

import { useState } from "react";
import { useTriggerJob } from "@/lib/hooks";
import { isBillingError } from "@/lib/api";
import { UpgradeModal } from "@/components/UpgradeModal";

// One consistent control for "run a background job" so every trigger across the console gives
// the SAME immediate feedback: the button disables and shows a spinner + "…ing" the instant
// it's clicked, killing the "did anything happen?" double-click problem. Pair it with the
// <JobProgressBanner/> at the top of the page to show live 0→100% progress + ETA.
export function RunJobButton({
  businessId,
  jobType,
  label,
  pendingLabel,
  className = "",
  variant = "primary",
  disabled = false,
  title,
  onSuccess,
}: {
  businessId: number | null;
  jobType: string;
  label: string;
  /** shown while running; defaults to `${label}…` */
  pendingLabel?: string;
  className?: string;
  variant?: "primary" | "secondary";
  disabled?: boolean;
  title?: string;
  onSuccess?: () => void;
}) {
  const trigger = useTriggerJob(businessId);
  const [upgrade, setUpgrade] = useState<string | null>(null);
  const base =
    variant === "primary"
      ? "bg-slate-900 text-white hover:bg-slate-700"
      : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50";
  const run = () =>
    trigger.mutate(
      { jobType },
      {
        onSuccess,
        // A billing wall (402/429) becomes an upgrade prompt at the moment of intent.
        onError: (e) => { if (isBillingError(e)) setUpgrade(e.message); },
      },
    );
  // Don't also show the generic red error when we're showing the upgrade modal.
  const showGenericError = trigger.isError && !isBillingError(trigger.error);
  return (
    <span className="inline-flex flex-col items-end gap-1">
      <button
        type="button"
        title={title}
        disabled={disabled || trigger.isPending || !businessId}
        onClick={run}
        className={`inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition disabled:opacity-50 ${base} ${className}`}
      >
        {trigger.isPending && (
          <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden>
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
        )}
        {trigger.isPending ? pendingLabel ?? `${label}…` : label}
      </button>
      {showGenericError && (
        <span className="text-xs text-rose-600">Couldn’t start — try again.</span>
      )}
      {upgrade && <UpgradeModal message={upgrade} onClose={() => setUpgrade(null)} />}
    </span>
  );
}
