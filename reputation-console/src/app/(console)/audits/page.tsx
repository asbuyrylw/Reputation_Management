"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useAuditRuns } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { StatusBadge } from "@/components/SentimentBadge";

const fmtDate = (s: string | null) => (s ? new Date(s).toLocaleDateString() : "—");
const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);

export default function AuditsPage() {
  const { businessId } = useBusiness();
  const { data, isLoading, error } = useAuditRuns(businessId);

  if (isLoading || !data) return <Spinner />;
  if (error) return <p className="text-sm text-red-600">Could not load audits.</p>;

  return (
    <div>
      <PageHeader
        title="Audits & AI answers"
        subtitle="Each audit asks the AI engines about this business and scores their answers. Open a run to read the answers."
      />
      {data.length === 0 ? (
        <Card>
          <p className="text-sm text-gray-600">No audits have run yet.</p>
        </Card>
      ) : (
        <Card className="overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2">Date</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Goal alignment</th>
                <th className="px-4 py-2">Owned</th>
                <th className="px-4 py-2">Contested</th>
                <th className="px-4 py-2">Answers</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="px-4 py-2">{fmtDate(r.finished_at || r.started_at)}</td>
                  <td className="px-4 py-2">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="px-4 py-2">{r.goal_alignment == null ? "—" : r.goal_alignment.toFixed(2)}</td>
                  <td className="px-4 py-2">{pct(r.owned_rate)}</td>
                  <td className="px-4 py-2">{pct(r.contested_rate)}</td>
                  <td className="px-4 py-2">{r.n_answers}</td>
                  <td className="px-4 py-2 text-right">
                    <Link className="text-blue-600 hover:underline" href={`/audits/${r.id}`}>
                      View →
                    </Link>
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
