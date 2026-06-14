"use client";

import { useBusiness } from "@/lib/business";
import { useDiscoveryTargets } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";

export default function OutreachPage() {
  const { businessId } = useBusiness();
  const { data, isLoading } = useDiscoveryTargets(businessId);

  if (isLoading || !data) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Outreach targets"
        subtitle="Journalists, outlets, podcasts and communities to pitch — ranked by relevance to this business."
      />
      {data.length === 0 ? (
        <Card>
          <p className="text-sm text-gray-600">No outreach targets discovered yet.</p>
        </Card>
      ) : (
        <Card className="overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Channel</th>
                <th className="px-4 py-2">Outlet</th>
                <th className="px-4 py-2">Beat</th>
                <th className="px-4 py-2">Score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.map((t) => (
                <tr key={t.id} className="hover:bg-gray-50">
                  <td className="px-4 py-2">
                    {t.url ? (
                      <a href={t.url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
                        {t.name}
                      </a>
                    ) : (
                      t.name
                    )}
                  </td>
                  <td className="px-4 py-2">{t.channel}</td>
                  <td className="px-4 py-2">{t.outlet}</td>
                  <td className="px-4 py-2">{t.beat}</td>
                  <td className="px-4 py-2">{t.score == null ? "—" : t.score.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
