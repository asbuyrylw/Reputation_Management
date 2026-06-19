"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useAttribution, useMomentum, useShareOfVoice, useGapModel } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { ShareOfVoiceBar } from "@/components/ShareOfVoiceBar";
import { SourceMix } from "@/components/SourceMix";
import { DataSection, EmptyState } from "@/components/primitives";
import { Term } from "@/components/Term";

type Json = Record<string, unknown>;
type Movement = {
  domain: string;
  classification: string;
  prev_share?: number;
  current_share?: number;
  delta?: number;
  state?: string;
};
type Missing = { topic?: string };
type Thin = { claim?: string };
const arr = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);

export default function RankingsPage() {
  const { businessId } = useBusiness();
  const sov = useShareOfVoice(businessId);
  const momentum = useMomentum(businessId);
  const attr = useAttribution(businessId);
  const gap = useGapModel(businessId);

  if (sov.isLoading) return <Spinner />;

  const data = sov.data;
  const hasData = data && data.run_id != null;
  const contestedShare = data?.by_classification?.contested?.share ?? 0;
  const ownedShare = data?.by_classification?.owned?.share ?? 0;
  const contestedSources = (data?.top_domains ?? []).filter((d) => d.classification === "contested");
  const movements = (momentum.data?.movements as Movement[] | undefined) ?? [];
  const contestedMoves = movements.filter((m) => m.classification === "contested");
  const goodMoves = movements.filter(
    (m) => (["owned", "neutral"].includes(m.classification) && m.state === "rising") || (m.classification === "contested" && ["falling", "dropped"].includes(m.state ?? "")),
  );
  const badMoves = movements.filter(
    (m) => (m.classification === "contested" && ["rising", "new"].includes(m.state ?? "")) || (m.classification === "owned" && ["falling", "dropped"].includes(m.state ?? "")),
  );

  const gm = (gap.data?.model ?? {}) as Json;
  const planPages = arr<Missing>(gm.missing_owned_content).slice(0, 3).map((p) => p.topic).filter(Boolean);
  const planProof = arr<Thin>(gm.thin_corroboration).slice(0, 2).map((t) => t.claim).filter(Boolean);

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
            <p className="text-sm text-gray-800">
              Of every website AI quotes about you, <span className="font-semibold">{pct(ownedShare)}</span> is{" "}
              <Term name="owned content">your own</Term>, and{" "}
              <span className={`font-semibold ${contestedShare > 0.05 ? "text-rose-600" : "text-green-700"}`}>{pct(contestedShare)}</span>{" "}
              is <Term name="contested">critical / contested</Term>.{" "}
              {contestedShare <= 0.05
                ? "Critical sources are a small slice — good. Keep growing your own share."
                : "Critical sources are a meaningful slice — the priority is out-publishing them."}{" "}
              <span className="text-gray-500">(aim: keep critical under 5%.)</span>
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
                    <span className="font-medium text-gray-900">{d.domain}</span>
                    <span className="text-xs text-gray-600">{d.cite_count} citations · {pct(d.share)} of all</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-gray-700">
                {contestedShare > 0
                  ? `${pct(contestedShare)} of citations are critical, spread across smaller sources. `
                  : "No critical sources are being cited right now — good. "}
                <Link href="/audits" className="font-medium text-blue-600 hover:underline">See the actual answers →</Link>
              </p>
            )}
          </Card>

          {/* what KINDS of sources AI cites (source-type mix) */}
          {data!.by_source_type && <SourceMix bySource={data!.by_source_type} />}

          {/* how the plan addresses it */}
          {(planPages.length > 0 || planProof.length > 0) && (
            <Card className="border-blue-100 bg-blue-50/40">
              <h3 className="text-sm font-semibold text-gray-900">How your plan addresses this</h3>
              <ul className="mt-2 list-disc space-y-1 pl-6 text-sm text-gray-700">
                {planPages.map((p, i) => (
                  <li key={`p${i}`}><span className="font-medium">Crowd out the negatives</span> by publishing: {p}</li>
                ))}
                {planProof.map((p, i) => (
                  <li key={`c${i}`}><span className="font-medium">Earn outside proof</span> for: {p}</li>
                ))}
                <li><span className="font-medium">Boost the good</span> — grow your owned/neutral citations so they out-number the critical ones.</li>
              </ul>
              <Link href="/content/work-orders" className="mt-2 inline-block text-sm font-medium text-blue-600 hover:underline">
                See these as tracked tasks →
              </Link>
            </Card>
          )}

          {/* momentum: good news / bad news */}
          {movements.length > 0 && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Card>
                <h3 className="text-sm font-semibold text-green-700">Good news — gaining</h3>
                {goodMoves.length ? (
                  <ul className="mt-2 space-y-1 text-sm text-gray-800">
                    {goodMoves.slice(0, 6).map((m) => (
                      <li key={m.domain}>↑ {m.domain} <span className="text-xs text-gray-500">({m.classification})</span></li>
                    ))}
                  </ul>
                ) : <p className="mt-2 text-sm text-gray-500">No clear gainers yet.</p>}
              </Card>
              <Card>
                <h3 className="text-sm font-semibold text-rose-600">Watch — critical sources rising</h3>
                {badMoves.length ? (
                  <ul className="mt-2 space-y-1 text-sm text-gray-800">
                    {badMoves.slice(0, 6).map((m) => (
                      <li key={m.domain}>↑ {m.domain} <span className="text-xs text-gray-500">({m.classification})</span></li>
                    ))}
                  </ul>
                ) : <p className="mt-2 text-sm text-green-700">Nothing critical is rising. 👍</p>}
                {contestedMoves.length > 0 && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs font-medium text-gray-500 hover:text-gray-800">
                      ▸ See all critical sources ({contestedMoves.length})
                    </summary>
                    <ul className="mt-1 space-y-1 text-sm text-gray-700">
                      {contestedMoves.map((m) => (
                        <li key={m.domain}>
                          {m.domain} <span className="text-xs text-gray-500">({pct(m.current_share)}, {m.state})</span>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
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
                <thead className="text-left text-xs uppercase text-gray-500">
                  <tr>
                    <th className="py-1">Website</th>
                    <th className="py-1"><Term name="classification">Type</Term></th>
                    <th className="py-1"><Term name="cites">Citations</Term></th>
                    <th className="py-1"><Term name="share">Share</Term></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 text-gray-700">
                  {data!.top_domains.map((d) => (
                    <tr key={d.domain}>
                      <td className="py-1 font-medium text-gray-900">{d.domain}</td>
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
