"use client";

import { useBusiness } from "@/lib/business";
import { useIncidents } from "@/lib/hooks";
import { IncidentCard } from "@/components/IncidentCard";
import { Card, PageHeader, Spinner } from "@/components/ui";

export default function IncidentsPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useIncidents(businessId);

  if (isLoading || !data) return <Spinner />;
  const pending = data.filter((i) => i.status === "pending_human_review");

  return (
    <div>
      <PageHeader
        title="Incidents"
        subtitle="New contested mentions, triaged by severity with a drafted response — approve before anything is sent."
      />
      {data.length === 0 ? (
        <Card>
          <p className="text-sm text-gray-600">No incidents flagged.</p>
        </Card>
      ) : (
        <div className="space-y-3">
          {pending.length > 0 && (
            <div className="text-sm font-medium text-gray-700">Awaiting review ({pending.length})</div>
          )}
          {data.map((i) => (
            <IncidentCard key={i.id} incident={i} businessId={businessId} canEdit={canEdit} />
          ))}
        </div>
      )}
    </div>
  );
}
