"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useAttribution, useMomentum, useShareOfVoice } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { ShareOfVoiceBar } from "@/components/ShareOfVoiceBar";
import { DataSection, EmptyState } from "@/components/primitives";
import { Term } from "@/components/Term";

type Movement = {
  domain: string;
  classification: string;
  prev_share?: number;
  current_share?: number;
  delta?: number;
  state?: string;
};
const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);

export default function RankingsPage() {
  const { businessId } = useBusiness();
  const sov = useShareOfVoice(businessId);
  const momentum = useMomentum(businessId);
  const attr = useAttribution(businessId);

  if (sov.isLoading) return <Spinner />;

  const data = sov.data;
  const hasData = data && data.run_id != null;
  const contestedShare = data?.by_classification?.contested?.share ?? 0;
  const ownedShare = data?.by_classification?.owned?.share ?? 0;
  const contestedSources = (data?.top_domains ?? []).filter((d) => d.classification === "contested");
  const movements = (momentum.data?.movements as Movement[] | undefined) ?? [];
  const goodMoves = movements.filter(
    (m) => (["owned", "neutral"].includes(m.classification) && m.state === "rising") || (m.classification === "contested" && ["falling", "dropped"].includes(m.state ?? "")),
  );
  const badMoves = movements.filter(
    (m) => (m.classification === "contested" && ["rising", "new"].includes(m.state ?? "")) || (m.classification === "owned" && ["falling", "dropped"].includes(m.state ?? "")),
  );

  return (
    <div>
      <PageHeader
        title="Who AI quotes about you"
        subtitle="When AI answers about you, it cites sources. This page shows whose sources are winning."
      />

      {!hasData ? (
        <EmptyState
          title="No citation data yet"
          why="We build this from the websites AI cited in your audit answers."
          produces="You'll see which share is your own content vs. neutral vs. critical sources."
          timing="Runs with each audit."
          cta={{ label: "Go to Run jobs", href: "/admin/jobs" }}
        />
      ) : (
        <div className="space-y-4">
          {/* verdict + share of voice */}
          <Card>
            <p className="text-sm text-gray-700">
              Of every website AI quotes about you, <span className="font-semibold">{pct(ownedShare)}</span> is{" "}
              <Term name="owned content">your own</Term>, and{" "}
              <span className={`font-semibold ${contestedShare > 0.05 ? "text-rose-600" : "text-green-700"}`}>{pct(contestedShare)}</span>{" "}
              is <Term name="contested">critical / contested</Term>.{" "}
              {contestedShare <= 0.05
                ? "Critical sources are a small slice — good. Keep growing your own share."
                : "Critical sources are a meaningful slice — the priority is out-publishing them."}
            </p>
            <div className="mt-3">
              <ShareOfVoiceBar byClass={data!.by_classification} />
            </div>
          </Card>

          {/* sources working against you */}
          <Card>
            <h3 className="text-sm font-semibold text-gray-900">Sources working against you</h3>
            {contestedSources.length > 0 ? (
              <ul className="mt-2 space-y-1.5">
                {contestedSources.map((d) => (
                  <li key={d.domain} className="flex items-center justify-between rounded-lg border border-rose-100 bg-rose-50/40 px-3 py-2 text-sm">
                    <span className="font-medium text-gray-800">{d.domain}</span>
                    <span className="text-xs text-gray-500">{d.cite_count} citations · {pct(d.share)} of all</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-gray-600">
                {contestedShare > 0
                  ? `${pct(contestedShare)} of citations are critical, spread across smaller sources. `
                  : "No critical sources are being cited right now — good. "}
                <Link href="/audits" className="font-medium text-blue-600 hover:underline">See the actual answers →</Link>
              </p>
            )}
          </Card>

          {/* momentum: good news / bad news */}
          {movements.length > 0 && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Card>
                <h3 className="text-sm font-semibold text-green-700">Good news — gaining</h3>
                {goodMoves.length ? (
                  <ul className="mt-2 space-y-1 text-sm text-gray-700">
                    {goodMoves.slice(0, 6).map((m) => (
                      <li key={m.domain}>↑ {m.domain} <span className="text-xs text-gray-400">({m.classification})</span></li>
                    ))}
                  </ul>
                ) : <p className="mt-2 text-sm text-gray-400">No clear gainers yet.</p>}
              </Card>
              <Card>
                <h3 className="text-sm font-semibold text-rose-600">Watch — critical sources rising</h3>
                {badMoves.length ? (
                  <ul className="mt-2 space-y-1 text-sm text-gray-700">
                    {badMoves.slice(0, 6).map((m) => (
                      <li key={m.domain}>↑ {m.domain} <span className="text-xs text-gray-400">({m.classification})</span></li>
                    ))}
                  </ul>
                ) : <p className="mt-2 text-sm text-green-700">Nothing critical is rising. 👍</p>}
              </Card>
            </div>
          )}

          {/* all cited sources */}
          {data!.top_domains.length > 0 && (
            <DataSection
              title="All cited sources"
              severity="low"
              headline="Every website AI quoted about you, most-cited first."
              highlights={[{ label: "Sources", value: String(data!.top_domains.length) }]}
              detailsLabel="See the full list"
            >
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-gray-400">
                  <tr>
                    <th className="py-1">Website</th>
                    <th className="py-1"><Term name="classification">Type</Term></th>
                    <th className="py-1"><Term name="cites">Citations</Term></th>
                    <th className="py-1"><Term name="share">Share</Term></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {data!.top_domains.map((d) => (
                    <tr key={d.domain}>
                      <td className="py-1">{d.domain}</td>
                      <td className="py-1 capitalize">{d.classification}</td>
                      <td className="py-1">{d.cite_count}</td>
                      <td className="py-1">{pct(d.share)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </DataSection>
          )}

          {attr.data && attr.data.length > 0 && (
            <Card>
              <h3 className="text-sm font-semibold text-gray-900">What moved since the work started</h3>
              <p className="mb-2 text-xs text-amber-700">A correlation — not proof of cause.</p>
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
      )}
    </div>
  );
}
