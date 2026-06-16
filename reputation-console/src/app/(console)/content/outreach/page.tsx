"use client";

import { useBusiness } from "@/lib/business";
import { useDiscoveryTargets } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";

function matchLabel(s: number | null): { label: string; cls: string } {
  if (s == null) return { label: "—", cls: "text-gray-400" };
  if (s >= 0.7) return { label: "High", cls: "text-green-700" };
  if (s >= 0.4) return { label: "Medium", cls: "text-amber-700" };
  return { label: "Low", cls: "text-gray-500" };
}

export default function OutreachPage() {
  const { businessId } = useBusiness();
  const { data, isLoading } = useDiscoveryTargets(businessId);

  if (isLoading || !data) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Outreach targets"
        subtitle="Journalists, outlets, and communities worth pitching — earning a mention from them builds the outside proof AI trusts."
      />
      {data.length === 0 ? (
        <EmptyState
          title="No outreach targets yet"
          why="These are people and outlets to pitch so they write about you — the third-party proof AI trusts."
          produces="Once discovery runs, you'll see ranked contacts with how good a match each is for your story."
          timing="Generated as part of the plan."
        />
      ) : (
        <Card className="overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Channel</th>
                <th className="px-4 py-2">Outlet</th>
                <th className="px-4 py-2">Covers</th>
                <th className="px-4 py-2">Match</th>
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
                  <td className={`px-4 py-2 font-medium ${matchLabel(t.score).cls}`}>{matchLabel(t.score).label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
