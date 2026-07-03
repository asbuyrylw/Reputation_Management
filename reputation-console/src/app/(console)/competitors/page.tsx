"use client";

import { useState, Fragment } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useBusiness } from "@/lib/business";
import { useCompetitors, useCompare, useAddCompetitor, useDeleteCompetitor, useTriggerJob, useLocalRankings } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState, ToneBar } from "@/components/primitives";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import type { LocalRankEntry } from "@/lib/types";

const pct = (v: number | undefined | null) => `${Math.round((v ?? 0) * 100)}%`;

// Compact "page 1 / page 2, position N" label for a SERP entry — the framing a business
// owner reads instantly (page 1 vs page 2), not a bare overall index.
function rankShort(e: LocalRankEntry | null | undefined): { text: string; tone: string } {
  if (!e || !e.found) return { text: "not in top 20", tone: "text-slate-400" };
  if (e.organic_rank != null) {
    const onePage = e.organic_rank <= 10;
    const pos = onePage ? e.organic_rank : e.organic_rank - 10;
    return { text: `#${e.organic_rank} (page ${onePage ? 1 : 2}, listing ${pos})`, tone: onePage ? "text-emerald-700" : "text-amber-600" };
  }
  if (e.local_pack_rank != null) return { text: `map pack #${e.local_pack_rank}`, tone: "text-emerald-700" };
  return { text: "listed", tone: "text-slate-500" };
}

// Local Google head-to-head: per local search, your position vs. the best-ranked rival.
function LocalSerpHeadToHead({ businessId }: { businessId: number | null }) {
  const ranks = useLocalRankings(businessId);
  const queries = ranks.data?.queries ?? [];
  if (queries.length === 0) return null;
  return (
    <Card accent="info">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Local Google rankings — you vs. them</h3>
          <p className="mt-1 text-sm text-slate-600">
            Where you and your rivals land on Google&apos;s first page for the local searches a nearby customer types.
            Page 1 is what wins clicks.
          </p>
        </div>
        <Link href="/local-seo" className="shrink-0 text-sm font-medium text-indigo-600 hover:text-indigo-700">
          Full local rankings →
        </Link>
      </div>
      <div className="mt-3 space-y-3">
        {queries.slice(0, 6).map((q) => {
          const me = rankShort(q.subject);
          const best = (q.competitors ?? []).filter((x) => x.found).sort((a, b) => (a.organic_rank ?? 99) - (b.organic_rank ?? 99))[0];
          return (
            <div key={q.query} className="border-t border-slate-100 pt-2.5 first:border-0 first:pt-0">
              <div className="text-sm font-medium text-slate-900">{q.query}</div>
              <div className="mt-1 flex flex-wrap gap-x-6 gap-y-1 text-sm">
                <span className="text-slate-600">You: <span className={`font-semibold ${me.tone}`}>{me.text}</span></span>
                {best && (
                  <span className="text-slate-600">
                    Top rival ({best.name}): <span className={`font-semibold ${rankShort(best).tone}`}>{rankShort(best).text}</span>
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

export default function CompetitorsPage() {
  const { businessId, canEdit } = useBusiness();
  const competitors = useCompetitors(businessId);
  const compare = useCompare(businessId);
  const add = useAddCompetitor(businessId);
  const del = useDeleteCompetitor(businessId);
  const bench = useTriggerJob(businessId);
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null); // which head-to-head row's questions are open

  if (competitors.isLoading) return <Spinner />;
  const comps = competitors.data ?? [];
  const c = compare.data ?? {};
  const standings = c.standings ?? [];
  const subject = standings.find((s) => s.is_subject);

  const runBench = () =>
    bench.mutate(
      { jobType: "benchmark" },
      { onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ["compare", businessId] }), 12000) },
    );

  return (
    <div>
      <PageHeader
        eyebrow="Benchmark"
        title="Competitors"
        subtitle="When AI answers questions in your category, how often does it surface YOU vs. your rivals?"
      />

      <JobProgressBanner businessId={businessId} className="mb-4" />

      {canEdit && (
        <Card className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-slate-600">Track rivals, then benchmark how often AI mentions each of you.</span>
            <button
              onClick={runBench}
              disabled={bench.isPending || comps.length === 0}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {bench.isPending ? "Benchmarking…" : "Run benchmark"}
            </button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Competitor name" className="min-w-[14rem] flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
            <input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="Domain (optional)" className="rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
            <button
              onClick={() => name.trim() && add.mutate({ name, domain }, { onSuccess: () => { setName(""); setDomain(""); } })}
              disabled={add.isPending || !name.trim()}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
            >
              Add competitor
            </button>
          </div>
          {comps.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {comps.map((cm) => (
                <span key={cm.id} className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700">
                  {cm.name}
                  <button onClick={() => del.mutate(cm.id)} className="text-slate-400 hover:text-slate-700" aria-label="remove">×</button>
                </span>
              ))}
            </div>
          )}
        </Card>
      )}

      {standings.length === 0 ? (
        <EmptyState
          title="No benchmark yet"
          why="Add the competitors you care about, then run a benchmark to see how often AI mentions you vs. them for category questions."
          produces="You'll get a ranked share-of-voice board and a head-to-head breakdown."
          timing="A benchmark runs against the AI engines and takes a few minutes."
        />
      ) : (
        <div className="space-y-4">
          {/* standings */}
          <Card>
            <p className="text-sm text-slate-800">
              AI surfaces <span className="font-semibold">{c.business}</span> in{" "}
              <span className="font-semibold">{pct(subject?.appearance_rate)}</span> of category questions — rank{" "}
              <span className={`font-semibold ${(c.subject_rank ?? 99) > 2 ? "text-rose-600" : "text-emerald-700"}`}>
                {c.subject_rank} of {c.field_size}
              </span>
              . {(c.subject_rank ?? 99) > Math.ceil((c.field_size ?? 1) / 2)
                ? "You're being out-surfaced — the plan's job is to close that gap."
                : "You're holding your own; keep widening the lead."}
            </p>
            <div className="mt-4 space-y-2.5">
              {standings.map((s) => (
                <div key={s.name}>
                  <div className="mb-1 flex items-baseline justify-between text-sm">
                    <span className={s.is_subject ? "font-bold text-slate-900" : "text-slate-700"}>
                      {s.name}{s.is_subject ? " (you)" : ""}
                    </span>
                    <span className="tabular-nums text-slate-600">{pct(s.appearance_rate)} · {s.appears_in} of {c.prompts_compared}</span>
                  </div>
                  <ToneBar pct={s.appearance_rate * 100} tone={s.is_subject ? "bad" : "neutral"} />
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs text-slate-400">
              Appearance rate = share of category questions where AI mentions the party by name or cites its site.
            </p>
          </Card>

          {/* how to read the two different numbers — directly answers "100% vs 84% yet +2 net?" */}
          <Card accent="info" className="bg-linear-to-br from-indigo-50/40 to-white">
            <h3 className="text-sm font-semibold text-slate-900">How to read these two numbers</h3>
            <p className="mt-1 text-sm leading-relaxed text-slate-600">
              They measure different things, so they can look contradictory but aren&apos;t:
            </p>
            <ul className="mt-2 space-y-1.5 text-sm text-slate-600">
              <li>
                <span className="font-semibold text-slate-800">Appearance rate</span> counts <em>every</em> question where AI
                mentions a party — including questions where it mentions <em>both</em> of you. A rival can be named in more
                questions overall (a higher %) simply by being mentioned alongside you.
              </li>
              <li>
                <span className="font-semibold text-slate-800">Head-to-head net</span> looks only at the questions where
                <em> exactly one</em> of you appears. You can still win more of those contested questions (a positive net)
                even when a rival&apos;s overall appearance rate is higher.
              </li>
            </ul>
            <p className="mt-2 text-xs text-slate-500">
              So &ldquo;rival 100%, you 84%, but you&apos;re +2&rdquo; means: they get mentioned in more answers overall, but
              among the answers that name only one of you, you come out ahead by 2.
            </p>
          </Card>

          {/* head to head — AI answers, explained in plain language */}
          {c.head_to_head && c.head_to_head.length > 0 && (
            <Card>
              <h3 className="text-base font-semibold tracking-tight text-slate-900">Head-to-head — AI answers</h3>
              <p className="mt-1 text-sm leading-relaxed text-slate-600">
                Of the category questions we ask AI, this is how you split the ones where only one of you shows up.
                <span className="font-semibold text-emerald-700"> &ldquo;Only you win&rdquo;</span> = AI named you but not them (good).
                <span className="font-semibold text-rose-600"> &ldquo;Only they win&rdquo;</span> = AI named them but not you — the gap to close.
                <span className="font-semibold text-slate-700"> Net</span> is the difference. Click a count to see the actual questions.
              </p>
              <table className="mt-3 w-full text-sm">
                <thead className="text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  <tr>
                    <th className="py-1.5">Competitor</th>
                    <th className="py-1.5 text-center">Only you win</th>
                    <th className="py-1.5 text-center">Only they win</th>
                    <th className="py-1.5 text-right">Net</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {c.head_to_head.map((h) => {
                    const net = (h.subject_only_prompts ?? 0) - (h.competitor_only_prompts ?? 0);
                    const isOpen = expanded === h.competitor;
                    const hasDetail = (h.prompts_subject_only?.length ?? 0) + (h.prompts_competitor_only?.length ?? 0) > 0;
                    return (
                      <Fragment key={h.competitor}>
                        <tr
                          className={`transition-colors ${hasDetail ? "cursor-pointer hover:bg-slate-50" : ""}`}
                          onClick={() => hasDetail && setExpanded(isOpen ? null : h.competitor)}
                        >
                          <td className="py-2 font-medium text-slate-900">
                            {hasDetail && <span className="mr-1 text-slate-400">{isOpen ? "▾" : "▸"}</span>}
                            {h.competitor}
                          </td>
                          <td className="py-2 text-center font-semibold tabular-nums text-emerald-700">{h.subject_only_prompts}</td>
                          <td className="py-2 text-center font-semibold tabular-nums text-rose-600">{h.competitor_only_prompts}</td>
                          <td className={`py-2 text-right font-bold tabular-nums ${net > 0 ? "text-emerald-600" : net < 0 ? "text-rose-600" : "text-slate-400"}`}>
                            {net > 0 ? `+${net}` : net}
                          </td>
                        </tr>
                        {isOpen && hasDetail && (
                          <tr>
                            <td colSpan={4} className="bg-slate-50/70 px-3 py-3">
                              <div className="grid gap-4 sm:grid-cols-2">
                                <QuestionList
                                  title="Questions only you win"
                                  tone="good"
                                  questions={h.prompts_subject_only ?? []}
                                />
                                <QuestionList
                                  title={`Questions only ${h.competitor} wins`}
                                  tone="bad"
                                  questions={h.prompts_competitor_only ?? []}
                                />
                              </div>
                              {(h.prompts_both?.length ?? 0) > 0 && (
                                <div className="mt-3">
                                  <QuestionList
                                    title="Questions where AI named both of you (ties)"
                                    tone="neutral"
                                    questions={h.prompts_both ?? []}
                                  />
                                </div>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </Card>
          )}

          {/* Local Google head-to-head (SERP positions, page-1/page-2 framing) */}
          <LocalSerpHeadToHead businessId={businessId} />
        </div>
      )}
    </div>
  );
}

function QuestionList({ title, tone, questions }: { title: string; tone: "good" | "bad" | "neutral"; questions: string[] }) {
  const dot = tone === "good" ? "bg-emerald-500" : tone === "bad" ? "bg-rose-500" : "bg-slate-400";
  return (
    <div>
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{title}</div>
      {questions.length === 0 ? (
        <p className="text-sm text-slate-400">—</p>
      ) : (
        <ul className="space-y-1">
          {questions.map((q, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
              <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} aria-hidden />
              <span>&ldquo;{q}&rdquo;</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
