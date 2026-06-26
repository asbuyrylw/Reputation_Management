"use client";

import { useState } from "react";
import Link from "next/link";
import { usePublishChannels, usePublishTargets, usePublishAsset, useRetryPublishTarget } from "@/lib/hooks";
import { ApiError } from "@/lib/api";
import type { PublishTarget } from "@/lib/types";

// Status -> small colored chip for a publish target.
function targetChip(status: string): string {
  switch (status) {
    case "published":
      return "bg-emerald-100 text-emerald-700";
    case "scheduled":
      return "bg-indigo-100 text-indigo-700";
    case "failed":
      return "bg-rose-100 text-rose-700";
    case "skipped":
      return "bg-slate-200 text-slate-500";
    default:
      return "bg-amber-100 text-amber-700"; // pending
  }
}

function TargetRow({
  t,
  businessId,
  assetId,
  canEdit,
}: {
  t: PublishTarget;
  businessId: number | null;
  assetId: number;
  canEdit: boolean;
}) {
  const retry = useRetryPublishTarget(businessId, assetId);
  return (
    <li className="flex flex-wrap items-center gap-2 text-xs">
      <span className={`rounded-full px-1.5 py-0.5 font-medium ${targetChip(t.status)}`}>
        {t.network || t.channel}
      </span>
      <span className="text-slate-500">{t.status}</span>
      {t.external_url ? (
        <a href={t.external_url} target="_blank" rel="noreferrer" className="break-all text-indigo-600 hover:underline">
          {t.external_url}
        </a>
      ) : t.scheduled_for ? (
        <span className="text-slate-400">for {new Date(t.scheduled_for).toLocaleString()}</span>
      ) : null}
      {t.last_error && <span className="text-rose-600">{t.last_error}</span>}
      {canEdit && t.status === "failed" && (
        <button
          onClick={() => retry.mutate(t.id)}
          disabled={retry.isPending}
          className="rounded border border-slate-300 px-1.5 py-0.5 text-[11px] text-slate-600 hover:bg-slate-100 disabled:opacity-50"
        >
          {retry.isPending ? "Retrying…" : "Retry"}
        </button>
      )}
    </li>
  );
}

// Compact, collapsible per-asset publishing panel: pick connected channels, publish now or
// schedule, then watch the resulting publish targets go live.
export function AssetPublishPanel({
  assetId,
  businessId,
  canEdit,
}: {
  assetId: number;
  businessId: number | null;
  canEdit: boolean;
}) {
  const [open, setOpen] = useState(false);
  const { data: channels } = usePublishChannels(businessId);
  const { data: targets } = usePublishTargets(businessId, open ? assetId : null);
  const publish = usePublishAsset(businessId, assetId);
  const retryEnabled = canEdit;

  const [selected, setSelected] = useState<string[]>([]);
  const [scheduleOn, setScheduleOn] = useState(false);
  const [scheduledFor, setScheduledFor] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const toggle = (ch: string) =>
    setSelected((s) => (s.includes(ch) ? s.filter((c) => c !== ch) : [...s, ch]));

  const connected = (channels ?? []).filter((c) => c.connected);
  const unconnected = (channels ?? []).filter((c) => !c.connected);

  const doPublish = () => {
    if (selected.length === 0) return;
    setNote(null);
    setErr(null);
    publish.mutate(
      { channels: selected, scheduled_for: scheduleOn && scheduledFor ? scheduledFor : null },
      {
        onSuccess: (res) => {
          const parts: string[] = [];
          if (res.created.length) parts.push(`${res.created.length} queued`);
          if (res.skipped.length) parts.push(`${res.skipped.length} skipped (${res.skipped.join(", ")})`);
          setNote(parts.join(" · ") || "Done.");
          setSelected([]);
        },
        onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't publish — try again."),
      },
    );
  };

  return (
    <div className="mt-3 border-t border-slate-100 pt-3">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-xs font-medium text-indigo-600 hover:text-indigo-700"
      >
        {open ? "▾ Hide publishing" : "▸ Publish this to your channels"}
      </button>

      {open && (
        <div className="mt-2">
          {!canEdit ? (
            <p className="text-xs text-slate-400">You don&apos;t have edit access for this business.</p>
          ) : (
            <>
              <div className="text-xs font-medium text-slate-500">Choose channels</div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {connected.map((c) => (
                  <button
                    key={c.channel}
                    onClick={() => toggle(c.channel)}
                    className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
                      selected.includes(c.channel)
                        ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                        : "border-slate-200 text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    {c.label}
                  </button>
                ))}
                {connected.length === 0 && (
                  <span className="text-xs text-slate-400">No channels connected yet.</span>
                )}
              </div>

              {unconnected.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-400">
                  <span>Not connected:</span>
                  {unconnected.map((c) => (
                    <Link key={c.channel} href="/integrations" className="text-indigo-600 hover:underline">
                      {c.label} — connect first →
                    </Link>
                  ))}
                </div>
              )}

              <div className="mt-2 flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-1 text-xs text-slate-600">
                  <input type="checkbox" checked={scheduleOn} onChange={(e) => setScheduleOn(e.target.checked)} /> Schedule
                </label>
                {scheduleOn && (
                  <input
                    type="datetime-local"
                    value={scheduledFor}
                    onChange={(e) => setScheduledFor(e.target.value)}
                    className="rounded border border-slate-300 px-2 py-1 text-xs"
                  />
                )}
                <button
                  onClick={doPublish}
                  disabled={publish.isPending || selected.length === 0 || (scheduleOn && !scheduledFor)}
                  className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50"
                >
                  {publish.isPending ? "Submitting…" : scheduleOn ? "Schedule" : "Publish now"}
                </button>
              </div>
              {note && <p className="mt-1.5 text-xs text-slate-500">{note}</p>}
              {err && <p className="mt-1.5 text-xs text-rose-600">{err}</p>}
            </>
          )}

          {/* live publish targets */}
          {targets && targets.length > 0 && (
            <div className="mt-3">
              <div className="text-xs font-medium text-slate-500">Where it went</div>
              <ul className="mt-1.5 space-y-1.5">
                {targets.map((t) => (
                  <TargetRow key={t.id} t={t} businessId={businessId} assetId={assetId} canEdit={retryEnabled} />
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
