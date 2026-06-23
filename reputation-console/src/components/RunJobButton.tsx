"use client";

import { useTriggerJob } from "@/lib/hooks";

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
  const base =
    variant === "primary"
      ? "bg-slate-900 text-white hover:bg-slate-700"
      : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50";
  return (
    <span className="inline-flex flex-col items-end gap-1">
      <button
        type="button"
        title={title}
        disabled={disabled || trigger.isPending || !businessId}
        onClick={() => trigger.mutate({ jobType }, { onSuccess })}
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
      {trigger.isError && (
        <span className="text-xs text-rose-600">Couldn’t start — try again.</span>
      )}
    </span>
  );
}
