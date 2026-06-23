"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useBusiness } from "@/lib/business";
import { useDiscoveryTargets, useTriggerJob, useAddDiscoveryTarget, useSetTargetStatus } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import { JobProgressBanner } from "@/components/JobProgressBanner";

function matchLabel(s: number | null): { label: string; cls: string } {
  if (s == null) return { label: "—", cls: "text-slate-400" };
  if (s >= 0.7) return { label: "High", cls: "text-emerald-700" };
  if (s >= 0.4) return { label: "Medium", cls: "text-amber-700" };
  return { label: "Low", cls: "text-slate-500" };
}

const STATUS_LABEL: Record<string, string> = {
  suggested: "Suggested",
  contacted: "Contacted",
  responded: "Responded",
  declined: "Declined",
};

export default function OutreachPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useDiscoveryTargets(businessId);
  const find = useTriggerJob(businessId);
  const add = useAddDiscoveryTarget(businessId);
  const setStatus = useSetTargetStatus(businessId);
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", outlet: "", url: "", beat: "" });

  if (isLoading || !data) return <Spinner />;

  const runFind = () =>
    find.mutate(
      { jobType: "discovery" },
      { onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ["discovery-targets", businessId] }), 10000) },
    );

  return (
    <div>
      <PageHeader
        title="Outreach targets"
        subtitle="Journalists, outlets, and communities worth pitching — earning a mention from them builds the outside proof AI trusts."
      />

      <JobProgressBanner businessId={businessId} className="mb-4" />

      {canEdit && (
        <Card className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-slate-600">
              Targets are found automatically by the Discovery agent — or add your own.
            </span>
            <div className="flex gap-2">
              <button
                onClick={runFind}
                disabled={find.isPending}
                className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
              >
                {find.isPending ? "Finding…" : "Find targets"}
              </button>
              <button
                onClick={() => setShowAdd((s) => !s)}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100"
              >
                {showAdd ? "Cancel" : "Add manually"}
              </button>
            </div>
          </div>
          {showAdd && (
            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
              <input placeholder="Name (journalist / outlet / podcast)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
              <input placeholder="Outlet / publication" value={form.outlet} onChange={(e) => setForm({ ...form, outlet: e.target.value })} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
              <input placeholder="URL" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
              <input placeholder="Beat / topic they cover" value={form.beat} onChange={(e) => setForm({ ...form, beat: e.target.value })} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
              <button
                onClick={() => form.name.trim() && add.mutate({ ...form, channel: "manual" }, { onSuccess: () => { setForm({ name: "", outlet: "", url: "", beat: "" }); setShowAdd(false); } })}
                disabled={add.isPending || !form.name.trim()}
                className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 sm:w-32"
              >
                Add target
              </button>
            </div>
          )}
        </Card>
      )}

      {data.length === 0 ? (
        <EmptyState
          title="No outreach targets yet"
          why="These are people and outlets to pitch so they write about you — the third-party proof AI trusts."
          produces="Click “Find targets” to have the Discovery agent search for relevant journalists, outlets, podcasts, and communities — or add your own."
          timing="Finding targets takes a moment."
        />
      ) : (
        <Card className="overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Channel</th>
                <th className="px-4 py-2">Outlet</th>
                <th className="px-4 py-2">Covers</th>
                <th className="px-4 py-2">Match</th>
                <th className="px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((t) => (
                <tr key={t.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2">
                    {t.url ? (
                      <a href={t.url} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">{t.name}</a>
                    ) : (
                      t.name
                    )}
                  </td>
                  <td className="px-4 py-2">{t.channel}</td>
                  <td className="px-4 py-2">{t.outlet}</td>
                  <td className="px-4 py-2">{t.beat}</td>
                  <td className={`px-4 py-2 font-medium ${matchLabel(t.score).cls}`}>{matchLabel(t.score).label}</td>
                  <td className="px-4 py-2">
                    {canEdit ? (
                      <select
                        value={t.status ?? "suggested"}
                        onChange={(e) => setStatus.mutate({ targetId: t.id, status: e.target.value })}
                        className="rounded border border-slate-200 px-1.5 py-0.5 text-xs"
                      >
                        {Object.entries(STATUS_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                      </select>
                    ) : (
                      STATUS_LABEL[t.status ?? "suggested"] ?? t.status
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
