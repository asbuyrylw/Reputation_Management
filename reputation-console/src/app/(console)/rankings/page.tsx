"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useAttribution, useMomentum, useShareOfVoice, useGapModel } from "@/lib/hooks";
import { Card, PageHeader, Pill, Spinner, StatTile } from "@/components/ui";
import { ShareOfVoiceBar } from "@/components/ShareOfVoiceBar";
import { SourceMix } from "@/components/SourceMix";
import { DataSection, EmptyState } from "@/components/primitives";
import { Term } from "@/components/Term";
import type { Tone } from "@/lib/uiTokens";

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
// finer precision for share momentum, where whole-percent rounding hides the change
const pct1 = (v: number | null | undefined) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);

// "was 2.1% → now 3.5% (+1.4pp)" — the actual change behind a rising/falling pill, so the
// owner can see WHAT changed, not just a direction word.
function fmtMove(m: Movement): string | null {
  if (m.prev_share == null && m.current_share == null) return null;
  if (m.state === "new") return `new this audit — now ${pct1(m.current_share)}`;
  if (m.state === "dropped") return `was ${pct1(m.prev_share)} → no longer cited`;
  const dpp = Math.round(((m.current_share ?? 0) - (m.prev_share ?? 0)) * 1000) / 10;
  return `was ${pct1(m.prev_share)} → now ${pct1(m.current_share)} (${dpp >= 0 ? "+" : ""}${dpp}pp)`;
}

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
  const neutralShare = data?.by_classification?.neutral?.share ?? Math.max(0, 1 - ownedShare - contestedShare);
  const contestedSources = (data?.top_domains ?? []).filter((d) => d.classification === "contested");
  const movements = (momentum.data?.movements as Movement[] | undefined) ?? [];
  const contestedMoves = movements.filter((m) => m.classification === "contested");
  const goodMoves = movements.filter(
    (m) => (["owned", "neutral"].includes(m.classification) && m.state === "rising") || (m.classification === "contested" && ["falling", "dropped"].includes(m.state ?? "")),
  );
  // Owned/neutral sources losing ground — the contested ones are surfaced in their own section.
  const ownedSlipping = movements.filter(
    (m) => ["owned", "neutral"].includes(m.classification) && ["falling", "dropped"].includes(m.state ?? ""),
  );
  const moveTone = (state: string | undefined): Tone =>
    ["rising", "new"].includes(state ?? "") ? "bad" : ["falling", "dropped"].includes(state ?? "") ? "good" : "neutral";

  const gm = (gap.data?.model ?? {}) as Json;
  const planPages = arr<Missing>(gm.missing_owned_content).slice(0, 3).map((p) => p.topic).filter(Boolean);
  const planProof = arr<Thin>(gm.thin_corroboration).slice(0, 2).map((t) => t.claim).filter(Boolean);

  return (
    <div>
      <PageHeader
        eyebrow="Rankings"
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
          {/* Share of voice — who AI is quoting about you, at a glance */}
          <Card>
            <h3 className="text-base font-semibold tracking-tight text-slate-900">Share of voice</h3>
            <p className="mt-0.5 text-sm text-slate-500">Of every website AI quotes about you, here&apos;s who owns the conversation.</p>
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
              <StatTile
                label="Your own"
                value={pct(ownedShare)}
                tone="good"
                bar={Math.round(ownedShare * 100)}
                hint="Content from channels you control. Higher is better."
              />
              <StatTile
                label="Neutral"
                value={pct(neutralShare)}
                tone="neutral"
                bar={Math.round(neutralShare * 100)}
                hint="Third-party sources that aren't taking a side."
              />
              <StatTile
                label="Contested"
                value={pct(contestedShare)}
                tone={contestedShare > 0.05 ? "bad" : "good"}
                bar={Math.round(contestedShare * 100)}
                hint="Critical sources. Aim to keep this under 5%."
              />
            </div>
            <div className="mt-4">
              <ShareOfVoiceBar byClass={data!.by_classification} />
            </div>
          </Card>

          {/* Contested — pulled into its own dedicated section */}
          <Card accent="bad" className="bg-linear-to-br from-rose-50/50 to-white">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2.5">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-rose-100 text-rose-600" aria-hidden>
                    <svg viewBox="0 0 20 20" fill="currentColor" className="h-4.5 w-4.5"><path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 8a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" /></svg>
                  </span>
                  <h3 className="text-base font-semibold tracking-tight text-slate-900">Contested sources working against you</h3>
                </div>
                <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-slate-600">
                  These critical sources are being quoted by AI about you. The fix isn&apos;t to remove them — it&apos;s to
                  out-publish them so your own content out-numbers theirs.
                </p>
              </div>
              <div className="shrink-0 rounded-2xl bg-white px-4 py-3 text-center ring-1 ring-rose-200">
                <div className={`text-3xl font-bold leading-none ${contestedShare > 0.05 ? "text-rose-600" : "text-emerald-600"}`}>
                  {pct(contestedShare)}
                </div>
                <div className="mt-1 text-[11px] font-medium text-slate-500">of all citations · aim &lt;5%</div>
              </div>
            </div>

            {contestedSources.length > 0 ? (
              <ul className="mt-4 space-y-2">
                {contestedSources.map((d, i) => (
                  <li
                    key={d.domain}
                    className="flex items-center justify-between gap-3 rounded-xl border border-rose-100 bg-white px-3.5 py-2.5"
                  >
                    <span className="flex min-w-0 items-center gap-2.5">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-rose-500 text-[11px] font-bold text-white">
                        {i + 1}
                      </span>
                      <span className="truncate text-sm font-semibold text-slate-900">{d.domain}</span>
                    </span>
                    <span className="shrink-0 text-xs font-medium text-slate-500">
                      {d.cite_count} citations · {pct(d.share)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-4 rounded-xl border border-emerald-100 bg-emerald-50/50 px-3.5 py-2.5 text-sm font-medium text-emerald-700">
                {contestedShare > 0
                  ? `${pct(contestedShare)} of citations are critical, spread across smaller sources — no single dominant offender.`
                  : "No critical sources are being cited right now — you're clean here. 👍"}
              </p>
            )}

            {contestedMoves.length > 0 && (
              <div className="mt-4">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Momentum of critical sources</div>
                <p className="mt-0.5 text-xs text-slate-500">
                  How each critical source&apos;s share of citations changed since your previous audit — ↑ rising is bad, ↓ falling is good.
                </p>
                <ul className="mt-2 space-y-1.5">
                  {contestedMoves.map((m) => {
                    const t = moveTone(m.state);
                    const chg = fmtMove(m);
                    return (
                      <li key={m.domain} className="flex flex-wrap items-center gap-2 text-sm">
                        <span className={`font-semibold ${t === "bad" ? "text-rose-600" : t === "good" ? "text-emerald-600" : "text-slate-400"}`}>
                          {t === "bad" ? "↑" : t === "good" ? "↓" : "•"}
                        </span>
                        <span className="font-medium text-slate-900">{m.domain}</span>
                        <Pill tone={t}>{m.state}</Pill>
                        {chg && <span className="text-xs text-slate-500">{chg}</span>}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            <div className="mt-4 flex flex-wrap gap-4">
              <Link href="/content/work-orders" className="inline-flex items-center gap-1 text-sm font-semibold text-rose-600 hover:text-rose-700">
                Out-publish these sources →
              </Link>
              <Link
                href={
                  data!.run_id != null
                    ? `/audits/${data!.run_id}${contestedSources[0] ? `?source_domain=${encodeURIComponent(contestedSources[0].domain)}` : ""}`
                    : "/audits"
                }
                className="inline-flex items-center gap-1 text-sm font-medium text-slate-500 hover:text-slate-700"
              >
                {contestedSources[0] ? `See the answers citing ${contestedSources[0].domain} →` : "See the actual answers →"}
              </Link>
            </div>
          </Card>

          {/* what KINDS of sources AI cites (source-type mix) */}
          {data!.by_source_type && <SourceMix bySource={data!.by_source_type} />}

          {/* how the plan addresses it */}
          {(planPages.length > 0 || planProof.length > 0) && (
            <Card accent="info" className="bg-linear-to-br from-indigo-50/50 to-white">
              <h3 className="text-base font-semibold tracking-tight text-slate-900">How your plan addresses this</h3>
              <ul className="mt-3 space-y-2.5 text-sm text-slate-700">
                {planPages.map((p, i) => (
                  <li key={`p${i}`} className="flex gap-2.5">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-500" aria-hidden />
                    <span><span className="font-semibold text-slate-900">Crowd out the negatives</span> by publishing: {p}</span>
                  </li>
                ))}
                {planProof.map((p, i) => (
                  <li key={`c${i}`} className="flex gap-2.5">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-500" aria-hidden />
                    <span><span className="font-semibold text-slate-900">Earn outside proof</span> for: {p}</span>
                  </li>
                ))}
                <li className="flex gap-2.5">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" aria-hidden />
                  <span><span className="font-semibold text-slate-900">Boost the good</span> — grow your owned/neutral citations so they out-number the critical ones.</span>
                </li>
              </ul>
              <Link href="/content/work-orders" className="mt-3 inline-block text-sm font-semibold text-indigo-600 hover:text-indigo-700">
                See these as tracked tasks →
              </Link>
            </Card>
          )}

          {/* momentum: good news / watch */}
          {movements.length > 0 && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Card accent="good">
                <h3 className="flex items-center gap-2 text-base font-semibold tracking-tight text-slate-900">
                  <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" aria-hidden /> Moving your way
                </h3>
                <p className="mt-0.5 text-xs text-slate-500">
                  Your own/neutral sources getting cited more, or critical sources getting cited less, since your last audit.
                </p>
                {goodMoves.length ? (
                  <ul className="mt-3 space-y-1.5 text-sm text-slate-700">
                    {goodMoves.slice(0, 6).map((m) => {
                      const chg = fmtMove(m);
                      return (
                        <li key={m.domain} className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold text-emerald-600">{m.classification === "contested" ? "↓" : "↑"}</span>
                          <span className="font-medium text-slate-900">{m.domain}</span>
                          <Pill tone="neutral">{m.classification}</Pill>
                          {chg && <span className="text-xs text-slate-500">{chg}</span>}
                        </li>
                      );
                    })}
                  </ul>
                ) : <p className="mt-3 text-sm text-slate-500">No clear gainers yet.</p>}
              </Card>
              <Card accent={ownedSlipping.length ? "bad" : "good"}>
                <h3 className="flex items-center gap-2 text-base font-semibold tracking-tight text-slate-900">
                  <span className={`h-2.5 w-2.5 rounded-full ${ownedSlipping.length ? "bg-rose-500" : "bg-emerald-500"}`} aria-hidden /> Your sources cited less than last audit
                </h3>
                <p className="mt-0.5 text-xs text-slate-500">
                  Your own/neutral sources whose share of AI citations dropped — worth a fresh post or refresh so they keep getting quoted.
                </p>
                {ownedSlipping.length ? (
                  <ul className="mt-3 space-y-1.5 text-sm text-slate-700">
                    {ownedSlipping.slice(0, 6).map((m) => {
                      const chg = fmtMove(m);
                      return (
                        <li key={m.domain} className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold text-rose-600">↓</span>
                          <span className="font-medium text-slate-900">{m.domain}</span>
                          <Pill tone="neutral">{m.classification}</Pill>
                          {chg && <span className="text-xs text-slate-500">{chg}</span>}
                        </li>
                      );
                    })}
                  </ul>
                ) : <p className="mt-3 text-sm font-medium text-emerald-700">None of your sources are slipping. 👍</p>}
              </Card>
            </div>
          )}

          {/* B3: turn citation gaps into outreach */}
          {data!.top_domains.length > 0 && (
            <Card className="bg-linear-to-br from-indigo-50/40 to-white">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold text-slate-900">Want AI to cite you more?</h3>
                  <p className="mt-0.5 text-xs text-slate-500">
                    AI quotes the sources above. To get onto more of them — and earn the third-party
                    coverage and links that move your score — work your outreach list.
                  </p>
                </div>
                <Link href="/content/outreach" className="shrink-0 rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700">
                  Find outreach targets →
                </Link>
              </div>
            </Card>
          )}

          {/* all cited sources */}
          {data!.top_domains.length > 0 && (
            <DataSection
              title="All cited sources"
              severity="low"
              headline="Every website AI quoted about you, most-cited first. Click a source to read the answers that cited it."
              highlights={[{ label: "Sources", value: String(data!.top_domains.length) }]}
              detailsLabel="See the full list"
            >
              <table className="w-full text-sm">
                <thead className="text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  <tr>
                    <th className="py-1.5">Website</th>
                    <th className="py-1.5"><Term name="classification">Type</Term></th>
                    <th className="py-1.5 text-right"><Term name="cites">Citations</Term></th>
                    <th className="py-1.5 text-right"><Term name="share">Share</Term></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {data!.top_domains.map((d) => {
                    const t: Tone = d.classification === "contested" ? "bad" : d.classification === "owned" ? "good" : "neutral";
                    const href = data!.run_id != null ? `/audits/${data!.run_id}?source_domain=${encodeURIComponent(d.domain)}` : null;
                    return (
                      <tr key={d.domain} className="transition-colors hover:bg-slate-50">
                        <td className="py-2 font-medium text-slate-900">
                          {href ? (
                            <Link href={href} className="text-indigo-600 hover:text-indigo-700 hover:underline">{d.domain}</Link>
                          ) : (
                            d.domain
                          )}
                        </td>
                        <td className="py-2"><Pill tone={t}>{d.classification}</Pill></td>
                        <td className="py-2 text-right tabular-nums">{d.cite_count}</td>
                        <td className="py-2 text-right font-semibold tabular-nums text-slate-900">{pct(d.share)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </DataSection>
          )}

          {attr.data && attr.data.length > 0 && (
            <Card>
              <h3 className="text-base font-semibold tracking-tight text-slate-900">What moved since the work started</h3>
              <p className="mt-0.5 mb-3 inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700 ring-1 ring-inset ring-amber-200">
                A correlation — not proof of cause.
              </p>
              <ul className="space-y-1.5 text-sm text-slate-700">
                {attr.data.map((a, i) => {
                  const up = a.delta != null && a.delta > 0;
                  return (
                    <li key={i} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-1.5">
                      <span className="font-medium text-slate-900">{a.metric}</span>
                      <span className={`font-semibold tabular-nums ${a.delta == null ? "text-slate-400" : up ? "text-emerald-600" : "text-rose-600"}`}>
                        {a.delta == null ? "—" : (up ? "+" : "") + a.delta.toFixed(3)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
