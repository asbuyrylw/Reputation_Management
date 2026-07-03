"use client";

import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useDashboard, usePerEngine, useTimeline, useMetricsTrend, useAnswerLenses, useAnswerChanges, useRunAnswers, useCompare } from "@/lib/hooks";
import { PerEnginePanel } from "@/components/PerEnginePanel";
import { PerEngineTrend } from "@/components/PerEngineTrend";
import { ScorePanel, SecHead } from "@/components/DashboardV2";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState, DataSection } from "@/components/primitives";
import { repScore, repBand, dashboardScore } from "@/lib/repScore";
import { engineLabel } from "@/lib/engines";
import type { Challenge, Answer } from "@/lib/types";

type Json = Record<string, unknown>;

const scoreColor = (s: number | null) => (s == null ? "#94A3B8" : s >= 60 ? "#059669" : s >= 40 ? "#D97706" : "#E0672E");
const asPct = (v: number | null | undefined) => (v == null ? null : v <= 1 ? Math.round(v * 100) : Math.round(v));

function LinkCard({ href, title, desc }: { href: string; title: string; desc: string }) {
  return (
    <Link href={href} className="group flex flex-col rounded-2xl border border-line bg-card p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition hover:-translate-y-0.5 hover:border-indigo hover:shadow-md">
      <span className="text-sm font-semibold text-ink group-hover:text-indigo">{title} →</span>
      <span className="mt-0.5 text-xs text-ink-3">{desc}</span>
    </Link>
  );
}

// "What it means" — the primary-challenge read: two-track pill + headline + the two driving metrics.
function WhatItMeans({ challenge }: { challenge?: Challenge | null }) {
  const trackLabel = challenge?.track === "both" ? "Two-track" : challenge?.label ?? "—";
  const recog = asPct(challenge?.signals?.recognition_gap);
  const neg = asPct(challenge?.signals?.negative_score ?? challenge?.signals?.negative_rate);
  return (
    <div className="rounded-[18px] border border-line bg-card p-7 px-[26px] shadow-[0_1px_2px_rgba(15,23,42,0.04),0_4px_16px_-6px_rgba(15,23,42,0.08)]">
      <div className="mb-3 flex items-center justify-between">
        <div className="eyebrow">What it means</div>
        <span className="rounded-full bg-indigo-050 px-2.5 py-1 font-mono text-[11px] font-semibold text-indigo-strong">{trackLabel}</span>
      </div>
      <p className="mb-5 text-[14px] leading-relaxed text-ink-2">{challenge?.headline ?? challenge?.recommendation ?? "Run an audit to see what's driving your AI reputation."}</p>
      {(recog != null || neg != null) && (
        <div className="space-y-3">
          {recog != null && <MetricLine label="Recognition gap" value={recog} suffix="gap" color="var(--amber)" />}
          {neg != null && <MetricLine label="Negative narrative" value={neg} suffix="neg" color="var(--alert)" />}
        </div>
      )}
    </div>
  );
}

function MetricLine({ label, value, suffix, color }: { label: string; value: number; suffix: string; color: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="min-w-0 flex-1">
        <div className="mb-1.5 text-[13px] font-medium text-ink-2">{label}</div>
        <div className="h-2 overflow-hidden rounded-full bg-line"><i className="block h-full rounded-full" style={{ width: `${Math.max(2, Math.min(100, value))}%`, background: color }} /></div>
      </div>
      <div className="flex shrink-0 items-baseline gap-1 font-display text-[22px] font-semibold tracking-[-0.02em]" style={{ color }}>
        {value}<small className="font-mono text-[11px] font-normal text-ink-4">{suffix}</small>
      </div>
    </div>
  );
}

// "AI Visibility" hub Overview — the enriched, flipped view: score hero, per-engine boxes, the
// worst answers right now, and the signals from prompts / citations / competitors. Deeper analysis
// (changes, per-engine trend, divergence, audiences) collapses into a detail section below.
export default function AiOverviewPage() {
  const { businessId, businesses, loading } = useBusiness();
  const { data, isLoading } = useDashboard(businessId);
  const latestRunId = data?.series?.length ? data.series[data.series.length - 1].run_id : null;
  const { data: perEngine } = usePerEngine(businessId, latestRunId);
  const { data: timeline } = useTimeline(businessId);
  const { data: trend } = useMetricsTrend(businessId);
  const { data: lensData } = useAnswerLenses(businessId);
  const { data: answerChanges } = useAnswerChanges(businessId);
  const { data: answers } = useRunAnswers(businessId, latestRunId);
  const { data: compare } = useCompare(businessId);

  if (loading || (businessId != null && (isLoading || !data))) return <Spinner />;
  if (businesses.length === 0 || !data) {
    return (
      <div>
        <PageHeader eyebrow="AI Visibility · Overview" title="How AI sees you" />
        <EmptyState title="No data yet" why="Set up a business and run an audit to see how AI assistants portray you." cta={{ label: "Set up a business", href: "/onboarding" }} />
      </div>
    );
  }

  const s = data.series;
  const latest = s[s.length - 1];
  const { score, deltaVsLast } = dashboardScore(s);
  const goalScore = repScore((timeline as Json | undefined)?.dominance_target as number);
  const aiExp = ((timeline as Json | undefined)?.projection as Json | undefined)?.expected as Json | undefined;
  const aiDate = aiExp?.target_date as string | undefined;
  const aiMonths = (aiExp?.months as number | undefined) ?? null;

  const engines = perEngine
    ? Object.entries(perEngine.engines).map(([key, m]) => {
        const sc = repScore(m.goal_alignment?.mean ?? null);
        return { key, score: sc, band: repBand(sc), contested: m.contested_rate?.p ?? null };
      }).sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    : [];

  const worstAnswers: Answer[] = (answers ?? [])
    .filter((a) => !a.failed && a.goal_alignment != null)
    .sort((a, b) => (a.goal_alignment ?? 0) - (b.goal_alignment ?? 0))
    .slice(0, 3);

  const weak = ((data.gap as unknown as { weak_queries?: { prompt?: string; problem?: string }[] } | undefined)?.weak_queries) ?? [];
  const owned = latest ? asPct(latest.owned_rate) : null;
  const contested = latest ? asPct(latest.contested_rate) : null;
  const neutral = owned != null && contested != null ? Math.max(0, 100 - owned - contested) : null;

  const standings = (compare?.standings ?? []).slice().sort((a, b) => b.appearance_rate - a.appearance_rate);
  const rank = compare?.subject_rank ?? null;
  const field = compare?.field_size ?? standings.length;

  return (
    <div>
      <PageHeader eyebrow="AI Visibility · Overview" title="How AI sees you" subtitle="Your AI reputation at a glance — the score, what's driving it, how each assistant answers, and the signals from prompts, citations and competitors." />

      <JobProgressBanner businessId={businessId} className="mb-4" />

      {!latest ? (
        <EmptyState title="No audit has run yet" why="An audit checks what ChatGPT, Claude, Perplexity, and Gemini say about your business." produces="Your score, per-engine breakdown, the worst answers, and the signals appear here once it finishes." cta={{ label: "Run an audit", href: "/runs" }} />
      ) : (
        <div className="space-y-2">
          {/* HERO flipped — score (big) beside "what it means" */}
          <section className="mb-5 grid grid-cols-1 gap-5 lg:grid-cols-[1.5fr_1fr]">
            <ScorePanel score={score} delta={deltaVsLast} goalScore={goalScore} aiDate={aiDate} aiMonths={aiMonths} />
            <WhatItMeans challenge={data.challenge} />
          </section>

          {/* How each assistant answers — boxed per-engine scores */}
          <SecHead title="How each assistant answers" note="the same questions, five very different answers" />
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {engines.length === 0 ? (
              <Card className="col-span-full text-sm text-ink-4">No per-engine scores yet.</Card>
            ) : (
              engines.map((e) => (
                <div key={e.key} className="rounded-[14px] border-2 bg-card p-3.5 text-center shadow-[0_1px_2px_rgba(15,23,42,0.04)]" style={{ borderColor: `${scoreColor(e.score)}40` }}>
                  <div className="mb-2 text-[13px] font-semibold text-ink">{engineLabel(e.key)}</div>
                  <div className="mx-auto mb-1.5 grid h-11 w-11 place-items-center rounded-full font-display text-[19px] font-semibold" style={{ background: `${scoreColor(e.score)}18`, color: scoreColor(e.score) }}>{e.score ?? "—"}</div>
                  <div className="font-mono text-[10.5px] uppercase tracking-[0.04em] text-ink-4">{e.band.label}</div>
                </div>
              ))
            )}
          </div>

          {/* The worst things AI says right now — larger indented quotes */}
          <SecHead title="The worst things AI says right now" link={{ label: "Fix these in the plan", href: "/next-steps" }} />
          <div className="mb-7 space-y-3">
            {worstAnswers.length === 0 ? (
              <Card className="text-sm text-ink-4">No scored answers yet — run an audit.</Card>
            ) : (
              worstAnswers.map((a) => {
                const sc = repScore(a.goal_alignment);
                return (
                  <Card key={a.id}>
                    <div className="mb-2.5 flex items-center gap-2">
                      <span className="rounded-[5px] border border-line-2 bg-paper px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-ink-2">{engineLabel(a.engine)}</span>
                      {sc != null && <span className="font-mono text-[11px] font-semibold text-alert">{sc} / 100 · {a.entity_confusion ? "Wrong business" : a.awareness === false ? "Doesn't know you" : "Unfavorable"}</span>}
                    </div>
                    <div className="mb-2 text-[16px] font-semibold leading-snug tracking-[-0.01em] text-ink">“{a.prompt}”</div>
                    {a.answer_text && (
                      <div className="relative rounded-r-[10px] border-l-[3px] border-alert bg-alert-bg px-4 py-3 text-[14px] italic leading-relaxed text-ink-2">“{a.answer_text.slice(0, 260)}…”</div>
                    )}
                  </Card>
                );
              })
            )}
          </div>

          {/* The signals behind the score — prompts / citations / competitors */}
          <SecHead title="The signals behind the score" note="pulled from prompts, citations & competitors" />
          <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
            {/* prompts at risk */}
            <Card className="flex flex-col">
              <div className="mb-3 flex items-center justify-between"><h3 className="text-[15px] font-semibold text-ink">Prompts at risk</h3><Link href="/prompts" className="text-xs font-semibold text-indigo hover:text-indigo-strong">All →</Link></div>
              <div className="mb-1 font-display text-[32px] font-semibold leading-none tracking-[-0.02em] text-alert">{weak.length} <span className="font-mono text-[15px] text-ink-4">flagged</span></div>
              <p className="mb-3.5 text-[13px] text-ink-3">tracked questions return a negative or missing answer on at least one engine.</p>
              {weak[0]?.prompt && (
                <div className="mt-auto rounded-[11px] bg-alert-bg px-3 py-2.5">
                  <div className="text-[12.5px] font-semibold text-ink-2">“{weak[0].prompt}”</div>
                  {weak[0].problem && <div className="mt-1 font-mono text-[11px] text-alert">{weak[0].problem}</div>}
                </div>
              )}
            </Card>
            {/* who AI cites */}
            <Card className="flex flex-col">
              <div className="mb-3 flex items-center justify-between"><h3 className="text-[15px] font-semibold text-ink">Who AI cites</h3><Link href="/rankings" className="text-xs font-semibold text-indigo hover:text-indigo-strong">Details →</Link></div>
              {owned == null ? (
                <div className="text-[13px] text-ink-4">No citations scored yet.</div>
              ) : (
                <>
                  <div className="mb-3 flex h-8 overflow-hidden rounded-[9px] font-mono text-[11px] font-semibold text-white">
                    {owned > 0 && <div className="grid place-items-center bg-indigo" style={{ width: `${Math.max(owned, 8)}%` }}>{owned}%</div>}
                    <div className="grid place-items-center bg-slate-300 text-ink-2" style={{ width: `${Math.max(neutral ?? 0, 6)}%` }}>{neutral}%</div>
                    {contested != null && contested > 0 && <div className="grid place-items-center bg-alert" style={{ width: `${Math.max(contested, 8)}%` }}>{contested}%</div>}
                  </div>
                  <div className="space-y-2 text-[13px]">
                    <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-sm bg-indigo" />Owned<b className="ml-auto font-mono">{owned}%</b></div>
                    <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-sm bg-slate-300" />Neutral<b className="ml-auto font-mono">{neutral}%</b></div>
                    <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-sm bg-alert" />Contested<b className={`ml-auto font-mono ${(contested ?? 0) < 5 ? "text-good" : "text-alert"}`}>{contested ?? 0}%</b></div>
                  </div>
                </>
              )}
            </Card>
            {/* vs rivals */}
            <Card className="flex flex-col">
              <div className="mb-3 flex items-center justify-between"><h3 className="text-[15px] font-semibold text-ink">Vs. rivals</h3><Link href="/competitors" className="text-xs font-semibold text-indigo hover:text-indigo-strong">Benchmark →</Link></div>
              {standings.length === 0 ? (
                <div className="text-[13px] text-ink-4">Add competitors to benchmark your share.</div>
              ) : (
                <>
                  {rank != null && <div className="mb-1 font-display text-[32px] font-semibold leading-none tracking-[-0.02em] text-ink">{rank}<span className="text-[17px] text-ink-4">{rank % 10 === 1 && rank % 100 !== 11 ? "st" : rank % 10 === 2 ? "nd" : rank % 10 === 3 ? "rd" : "th"}</span> <span className="font-mono text-[15px] text-ink-4">of {field}</span></div>}
                  <p className="mb-3.5 text-[13px] text-ink-3">how often AI surfaces you vs. the rivals you track.</p>
                  <div className="mt-auto space-y-1.5">
                    {standings.slice(0, 4).map((st, i) => (
                      <div key={st.name} className={`flex items-center gap-2 text-[12.5px] ${st.is_subject ? "font-bold" : ""}`}>
                        <span className="w-3.5 shrink-0 font-mono text-ink-4">{i + 1}</span>
                        <span className={`min-w-0 flex-1 truncate ${st.is_subject ? "text-indigo-strong" : "text-ink-2"}`}>{st.is_subject ? "You" : st.name}</span>
                        <span className="shrink-0 font-mono text-ink-3">{Math.round(st.appearance_rate * 100)}%</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </Card>
          </div>

          {/* Supporting detail — collapsed. The deep dives live in the AI hub tabs. */}
          <DataSection title="More detail — engines, changes & audiences" headline="Per-engine breakdown, what changed since the last audit, where engines disagree, and how different audiences see you." detailsLabel="Show detail">
            <div className="space-y-6">
              {answerChanges?.summary?.compared && (
                <Card>
                  <div className="mb-1 text-base font-semibold tracking-tight text-ink">What changed in AI answers</div>
                  <p className="mb-3 text-xs text-ink-3">How specific answers moved since your previous audit — the wins to build on and the regressions to fix.</p>
                  {answerChanges.changes.length === 0 ? (
                    <p className="rounded-md bg-paper px-3 py-2 text-sm text-ink-3">No material changes since the last audit — answers held steady.</p>
                  ) : (
                    <ul className="space-y-3">
                      {answerChanges.changes.slice(0, 6).map((ch, i) => {
                        const beforeGA = ch.before.goal_alignment;
                        const afterGA = ch.after.goal_alignment;
                        const improved = beforeGA != null && afterGA != null ? afterGA > beforeGA : null;
                        return (
                          <li key={i} className="rounded-xl border border-line bg-card px-3.5 py-2.5">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="rounded bg-ink px-1.5 py-0.5 text-[11px] font-medium text-white">{engineLabel(ch.engine)}</span>
                              <span className="min-w-0 truncate text-sm font-medium text-ink-2">“{ch.prompt}”</span>
                            </div>
                            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                              <span className="text-ink-4">Sentiment:</span>
                              <span className="text-ink-3">{ch.before.sentiment ?? "—"}</span>
                              <span className="text-ink-4">→</span>
                              <span className={`font-semibold ${ch.after.sentiment === "positive" ? "text-good" : ch.after.sentiment === "negative" ? "text-alert" : "text-ink-2"}`}>{ch.after.sentiment ?? "—"}</span>
                              {improved != null && <span className={`ml-1 font-semibold ${improved ? "text-good" : "text-alert"}`}>{improved ? "▲" : "▼"} goal alignment {beforeGA} → {afterGA}</span>}
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </Card>
              )}

              {perEngine && Object.keys(perEngine.engines).length > 0 && <PerEnginePanel data={perEngine} />}

              <Card>
                <div className="mb-1 text-base font-semibold tracking-tight text-ink">Each AI assistant over time</div>
                <p className="mb-3 text-xs text-ink-3">Spot a single engine drifting negative before it drags your overall score.</p>
                <PerEngineTrend data={trend} />
              </Card>

              {lensData?.divergence?.items && lensData.divergence.items.length > 0 && (
                <Card>
                  <div className="mb-1 text-base font-semibold tracking-tight text-ink">Where AI engines disagree most</div>
                  <p className="mb-3 text-xs text-ink-3">Same question, very different answers — the gap to close first.</p>
                  <ul className="space-y-2">
                    {lensData.divergence.items.slice(0, 5).map((d, i) => (
                      <li key={i} className="text-sm">
                        <div className="font-medium text-ink-2">“{d.prompt}”</div>
                        <div className="text-xs text-ink-3">
                          <span className="font-semibold text-good">{d.best_engine} {d.best}</span> vs <span className="font-semibold text-alert">{d.worst_engine} {d.worst}</span>
                          <span className="ml-1 text-ink-4">({d.spread}-pt gap)</span>
                          {d.contested_engines.length > 0 && <span className="ml-1 text-amber">· contested on {d.contested_engines.join(", ")}</span>}
                        </div>
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              {((lensData?.lenses?.by_persona?.length ?? 0) > 0 || (lensData?.lenses?.by_location?.length ?? 0) > 0) && (
                <Card>
                  <div className="mb-1 text-base font-semibold tracking-tight text-ink">How different audiences see you</div>
                  <p className="mb-3 text-xs text-ink-3">Whether a local prospect gets a worse answer than a generic one.</p>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    {[{ t: "By who's asking", rows: lensData!.lenses.by_persona }, { t: "By location", rows: lensData!.lenses.by_location }].map((g) =>
                      g.rows.length > 0 ? (
                        <div key={g.t}>
                          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-4">{g.t}</div>
                          <ul className="space-y-1">
                            {g.rows.map((r) => (
                              <li key={r.lens} className="flex items-center justify-between text-sm">
                                <span className="truncate text-ink-2">{r.lens}</span>
                                <span className="ml-2 shrink-0 font-semibold" style={{ color: scoreColor(r.score ?? 50) }}>{r.score ?? "—"}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      ) : null,
                    )}
                  </div>
                </Card>
              )}
            </div>
          </DataSection>

          <div className="pt-2">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-4">Go deeper</div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <LinkCard href="/audits" title="Audits & AI answers" desc="Every answer, scored by the judge." />
              <LinkCard href="/prompts" title="Prompts & topics" desc="The questions we ask AI about you." />
              <LinkCard href="/rankings" title="AI citations" desc="Which sources AI quotes about you." />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
