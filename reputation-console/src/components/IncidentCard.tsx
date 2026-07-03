"use client";

import { Card } from "./ui";
import { useResumeIncident } from "@/lib/hooks";
import type { Incident } from "@/lib/types";

const SEV: Record<string, string> = {
  high: "bg-rose-100 text-rose-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-slate-100 text-slate-700",
};

export function IncidentCard({
  incident,
  businessId,
  canEdit,
}: {
  incident: Incident;
  businessId: number | null;
  canEdit: boolean;
}) {
  const resume = useResumeIncident(businessId);
  const pending = incident.status === "pending_human_review";

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${SEV[incident.severity || ""] || "bg-slate-100 text-slate-700"}`}>
          {incident.severity} severity
        </span>
        {incident.sla_hours != null && <span className="text-xs text-slate-500">SLA {incident.sla_hours}h</span>}
        <span className="text-xs text-slate-400">{incident.status.replace(/_/g, " ")}</span>
      </div>
      {incident.mention_url && (
        <a href={incident.mention_url} target="_blank" rel="noreferrer" className="mt-1 block break-all text-sm text-indigo-600 hover:underline">
          {incident.mention_url}
        </a>
      )}
      {incident.draft_response && (
        <div className="mt-2 rounded bg-slate-50 p-3 text-sm text-slate-700">
          <div className="mb-1 text-xs font-semibold text-slate-500">Drafted response</div>
          {incident.draft_response}
        </div>
      )}
      {canEdit && pending && (
        <div className="mt-3 flex gap-2">
          <button
            disabled={resume.isPending}
            onClick={() => resume.mutate({ incidentId: incident.id, approved: true })}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Approve response
          </button>
          <button
            disabled={resume.isPending}
            onClick={() => resume.mutate({ incidentId: incident.id, approved: false })}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
          >
            Reject
          </button>
        </div>
      )}
      {resume.isError && (
        <p className="mt-2 text-xs text-amber-700">
          Resuming a review needs the durable checkpointer on the server (AGENT_CHECKPOINT_PG=1).
        </p>
      )}
    </Card>
  );
}
