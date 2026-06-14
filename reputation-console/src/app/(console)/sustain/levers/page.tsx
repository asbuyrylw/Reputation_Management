"use client";

import { useBusiness } from "@/lib/business";
import { useLearnedLevers } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";

export default function LeversPage() {
  const { businessId } = useBusiness();
  const { data, isLoading } = useLearnedLevers(businessId);

  if (isLoading || !data) return <Spinner />;
  const levers = Object.entries(data.levers || {}).sort((a, b) => b[1] - a[1]);

  return (
    <div>
      <PageHeader
        title="What's working"
        subtitle="Measured effectiveness of each tactic for THIS business — learned from your own results over time."
      />
      <Card className="mb-4">
        <div className="text-sm text-gray-700">
          Baseline monthly gain:{" "}
          <b>{data.baseline.monthly_gain == null ? "not enough data yet" : data.baseline.monthly_gain.toFixed(3)}</b>{" "}
          {data.baseline.confidence && <span className="text-xs text-gray-400">({data.baseline.confidence} confidence)</span>}
        </div>
      </Card>
      {levers.length === 0 ? (
        <Card>
          <p className="text-sm text-gray-600">Not enough observed history yet to rank tactics.</p>
        </Card>
      ) : (
        <Card>
          <div className="mb-2 text-sm font-medium text-gray-700">Lever effectiveness (gain per unit shipped)</div>
          <table className="w-full text-sm">
            <tbody className="divide-y divide-gray-100">
              {levers.map(([k, v]) => (
                <tr key={k}>
                  <td className="py-1.5">{k.replace(/_/g, " ")}</td>
                  <td className="py-1.5 text-right font-medium">{v.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
