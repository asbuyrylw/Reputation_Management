"use client";

import { useBusiness } from "@/lib/business";
import { useAttribution, useMomentum, useRootCause, useShareOfVoice } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { ShareOfVoiceBar } from "@/components/ShareOfVoiceBar";
import { DataBlocks } from "@/components/DataBlocks";

export default function RankingsPage() {
  const { businessId } = useBusiness();
  const sov = useShareOfVoice(businessId);
  const momentum = useMomentum(businessId);
  const rc = useRootCause(businessId);
  const attr = useAttribution(businessId);

  if (sov.isLoading) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Rankings & share of voice"
        subtitle="Which sources AI engines cite about you — and whether the owned ones are gaining while the contested ones fade."
      />
      <div className="space-y-6">
        <Card>
          <div className="mb-3 text-sm font-medium text-gray-700">Citation share of voice</div>
          {sov.data && sov.data.run_id != null ? (
            <>
              <ShareOfVoiceBar byClass={sov.data.by_classification} />
              {sov.data.top_domains.length > 0 && (
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left text-xs uppercase text-gray-400">
                      <tr>
                        <th className="py-1">Domain</th>
                        <th className="py-1">Class</th>
                        <th className="py-1">Cites</th>
                        <th className="py-1">Share</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {sov.data.top_domains.map((d) => (
                        <tr key={d.domain}>
                          <td className="py-1">{d.domain}</td>
                          <td className="py-1">{d.classification}</td>
                          <td className="py-1">{d.cite_count}</td>
                          <td className="py-1">{Math.round(d.share * 100)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-gray-500">No citation data yet — it's built from audit answers.</p>
          )}
        </Card>

        {rc.data && (
          <Card>
            <div className="mb-2 text-sm font-medium text-gray-700">Why the contested narrative surfaces</div>
            <DataBlocks data={rc.data.model} />
          </Card>
        )}

        {momentum.data && (
          <Card>
            <div className="mb-2 text-sm font-medium text-gray-700">Domain momentum</div>
            <DataBlocks data={momentum.data} />
          </Card>
        )}

        {attr.data && attr.data.length > 0 && (
          <Card>
            <div className="mb-1 text-sm font-medium text-gray-700">Attribution</div>
            <p className="mb-2 text-xs text-amber-700">Correlation — not proof of cause.</p>
            <ul className="space-y-1 text-sm text-gray-700">
              {attr.data.map((a, i) => (
                <li key={i}>
                  {a.metric}: {a.delta == null ? "—" : (a.delta > 0 ? "+" : "") + a.delta.toFixed(3)} over the window
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </div>
  );
}
