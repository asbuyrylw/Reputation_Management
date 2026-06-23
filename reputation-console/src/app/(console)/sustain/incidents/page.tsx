"use client";

import { useBusiness } from "@/lib/business";
import { useIncidents } from "@/lib/hooks";
import { IncidentCard } from "@/components/IncidentCard";
import { PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";

export default function IncidentsPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useIncidents(businessId);

  if (isLoading || !data) return <Spinner />;
  const pending = data.filter((i) => i.status === "pending_human_review");

  return (
    <div>
      <PageHeader
        title="Incidents"
        subtitle="New negative mentions worth a response, sorted by how urgent — with a draft reply you approve before anything is sent."
      />
      {data.length === 0 ? (
        <EmptyState
          title="No incidents to handle — good"
          why="When a serious negative mention appears, we flag it here with a suggested reply for your approval."
          produces="Nothing is ever sent without you. You'll see the mention, why it matters, and a draft response."
        />
      ) : (
        <div className="space-y-3">
          {pending.length > 0 && (
            <div className="text-sm font-medium text-slate-700">Awaiting review ({pending.length})</div>
          )}
          {data.map((i) => (
            <IncidentCard key={i.id} incident={i} businessId={businessId} canEdit={canEdit} />
          ))}
        </div>
      )}
    </div>
  );
}
