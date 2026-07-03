"use client";

// Plain-English replacement for the DataBlocks dump on Time to Goal. Leads with the ONE
// answer the owner wants — "when will it be fixed?" — then a you-are-here->goal bar, an
// explained confidence + recheck cue, and a ranked "speed it up" list. Raw methodology
// stays behind a details disclosure.

import { Card } from "./ui";
import { DataSection, ToneBar } from "./primitives";
import { Term } from "./Term";
import { repScore } from "@/lib/repScore";

type Json = Record<string, unknown>;
type Window = { months?: number; weeks?: number; target_date?: string };
type Lever = {
  lever?: string;
  unit?: string;
  suggested_per_month?: { low?: number; high?: number };
  weeks_saved_range?: { low?: number; high?: number };
  note?: string;
};

// Keys match the engine's acceleration levers (acceleration_advisor): earned_links,
// third_party_articles, earned_press, reviews, videos, podcasts -- plus older aliases.
const LEVER_LABELS: Record<string, string> = {
  earned_links: "Earned links (inbound links)",
  third_party_articles: "Third-party articles (published mentions)",
  earned_press: "Press / media coverage",
  reviews: "Genuine customer reviews",
  videos: "Video content",
  podcasts: "Podcast appearances",
  // older aliases kept so any legacy lever key still reads well
  press: "Press / media coverage",
  third_party_mentions: "Third-party mentions",
  directory_listings: "Directory & registry listings",
  social_proof: "Social proof",
};
// Concrete how-to + the plain-English definition. The two most-confused levers are spelled out:
// an EARNED LINK is a hyperlink FROM someone else's site back to yours; a THIRD-PARTY ARTICLE is
// a piece ABOUT you published on an outside outlet (which may or may not contain a link).
const LEVER_SUGGESTIONS: Record<string, string> = {
  earned_links:
    "A hyperlink FROM another website back to yours — it sends referral traffic and signals trust to AI and Google. e.g. a BBB / industry-directory listing, or a local press feature that links to your site.",
  third_party_articles:
    "An article ABOUT your business published on an outside outlet (a guest post or media mention) — outside corroboration of your story, which often also carries a link. e.g. a bylined post on a finance blog, or a local business feature.",
  earned_press:
    "e.g. pitch local Cincinnati business outlets; answer reporter queries on Connectively (HARO); offer an expert quote.",
  reviews:
    "e.g. ask satisfied clients for a Google review by email/SMS — genuine only, never incentivized against policy.",
  videos:
    "e.g. a short intro / testimonial video on YouTube + your site, cross-shared to social — owned content AI can surface and cite.",
  podcasts:
    "e.g. guest on a local-business or finance podcast; the episode page + show notes become citable third-party coverage.",
  press: "e.g. pitch local Cincinnati business outlets; answer reporter queries on Connectively (HARO); offer an expert quote.",
  third_party_mentions: "e.g. get listed/quoted on neutral finance sites, podcasts, and community Q&A where engines index.",
  directory_listings: "e.g. Google Business Profile, BBB, FINRA BrokerCheck, state DOI lookup, local chamber of commerce.",
  social_proof: "e.g. consistent posts + client testimonials on LinkedIn and your site that AI can cite.",
};
function leverLabel(k: string | undefined): string {
  if (!k) return "Action";
  return LEVER_LABELS[k] ?? k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// YYYY-MM-DD -> MM-DD-YYYY
function fmtDate(d?: string | null): string {
  if (!d) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
  return m ? `${m[2]}-${m[3]}-${m[1]}` : d;
}

function confidenceNote(c: string | undefined): string {
  if (c === "high") return "We've measured your real pace across several audits, so this date is firm.";
  if (c === "medium") return "Based on early measured movement — it'll firm up with another audit or two.";
  return "This is an early estimate from a baseline model. It sharpens after your next audit measures your real pace.";
}

export function TimelineView({ timeline, acceleration }: { timeline: Json; acceleration?: Json }) {
  const cur = repScore((timeline.current_alignment as number) ?? null);
  const goal = repScore((timeline.dominance_target as number) ?? null);
  const confidence = timeline.confidence as string | undefined;
  const proj = (timeline.projection as Json | undefined) ?? {};
  const expected = proj.expected as Window | undefined;
  const optimistic = proj.optimistic as Window | undefined;
  const conservative = proj.conservative as Window | undefined;
  const levers = (acceleration?.levers_ranked_by_impact as Lever[] | undefined) ?? [];

  return (
    <div className="space-y-4">
      {/* projected finish hero */}
      <Card>
        <div className="text-xs font-medium uppercase tracking-wide text-slate-400">Projected finish</div>
        <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-3xl font-bold text-slate-900">{fmtDate(expected?.target_date)}</span>
          <span className="text-sm text-slate-500">
            (~{expected?.months ?? "—"} months) to reach your goal of {goal ?? "—"}/100
          </span>
        </div>
        {(optimistic || conservative) && (
          <ul className="mt-2 list-disc space-y-0.5 pl-6 text-sm text-slate-600">
            <li>If things go well: <span className="font-medium text-slate-800">{fmtDate(optimistic?.target_date)}</span></li>
            <li>If slower: <span className="font-medium text-slate-800">{fmtDate(conservative?.target_date)}</span></li>
          </ul>
        )}
        {confidence && (
          <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm">
            <span className="font-medium text-slate-700">Confidence: {confidence}.</span>{" "}
            <span className="text-slate-600">{confidenceNote(confidence)}</span>
          </div>
        )}
        <p className="mt-2 text-xs text-slate-400">
          A projection, not a promise — it tracks how fast accurate content is out-publishing the negatives. Recheck after your next audit.
        </p>
      </Card>

      {/* you are here -> goal */}
      <Card>
        <div className="mb-2 flex items-center justify-between text-sm">
          <span className="font-medium text-slate-700">You are here → your goal</span>
          <span className="text-slate-500">{cur ?? "—"}/100 → {goal ?? "—"}/100</span>
        </div>
        <ToneBar pct={cur != null && goal ? Math.min(100, (cur / goal) * 100) : 0} tone="good" />
        <div className="mt-1 flex justify-between text-xs text-slate-400">
          <span>Today: {cur ?? "—"}</span>
          <span>Goal: {goal ?? "—"} (AI mostly accurate &amp; positive)</span>
        </div>
      </Card>

      {/* speed it up */}
      {levers.length > 0 && (
        <DataSection
          title="Speed it up"
          severity="low"
          headline="Outside actions that finish you sooner. Each shows how many weeks it could cut off — most impactful first."
          highlights={[{ label: "Options", value: String(levers.length) }]}
          defaultOpen
          detailsLabel="See the options"
        >
          <ul className="space-y-2">
            {levers.slice(0, 6).map((l, i) => {
              const ws = l.weeks_saved_range;
              const pm = l.suggested_per_month;
              const suggestion = LEVER_SUGGESTIONS[l.lever ?? ""];
              return (
                <li key={i} className="rounded-lg border border-slate-100 p-2.5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="text-sm font-semibold text-slate-800">{leverLabel(l.lever)}</div>
                    {ws && (
                      <span className="shrink-0 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                        saves {ws.low}–{ws.high} wks
                      </span>
                    )}
                  </div>
                  {pm && (
                    <div className="mt-0.5 text-xs text-slate-500">
                      Suggested: {pm.low}–{pm.high} per month{l.unit ? ` (${l.unit})` : ""}
                    </div>
                  )}
                  {suggestion && <div className="mt-1 text-xs text-slate-600">How: {suggestion}</div>}
                </li>
              );
            })}
          </ul>
        </DataSection>
      )}

      {/* methodology behind a disclosure — larger, bulleted */}
      <DataSection
        title="How this projection works"
        severity="good"
        headline="The date is driven by how entrenched the negatives are, how much accurate content is shipping, and your own measured pace once we have two audits."
        detailsLabel="See the methodology & assumptions"
      >
        <ul className="list-disc space-y-2 pl-6 text-base leading-relaxed text-slate-700">
          <li>
            <Term name="confidence">Confidence</Term> starts low and rises as your own measured pace accumulates across audits.
          </li>
          <li>Three things move the date: how entrenched the negatives are, how much accurate content is shipping, and your measured pace.</li>
          {timeline.gain_basis ? <li>Current basis: {String(timeline.gain_basis)}.</li> : null}
          <li>It estimates when the accurate narrative <span className="font-medium">dominates</span> what AI surfaces — drowning out, not removing, the negatives.</li>
          <li>AI-platform behavior and competitor activity can shift the timeline. It&apos;s a projection, not a promise.</li>
        </ul>
      </DataSection>
    </div>
  );
}
