"use client";

// v2 redesign — the flagship dashboard top: dark GOAL BANNER, a score-hero (big Fraunces gauge +
// path-to-goal) beside the worst answers, and the TWO GOALS row (AI reputation + local page-1).
// Faithful to the provided design HTML; wired to real data via props.

import Link from "next/link";
import type { ReactNode } from "react";
import type { Answer, LocalSeoGoal } from "@/lib/types";
import { repBand, repScore } from "@/lib/repScore";
import { engineLabel } from "@/lib/engines";

const fmtDate = (d?: string | null) => {
  if (!d) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
  if (!m) return d;
  return new Date(`${d.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
};
// Score color: weak = burnt-orange (design), amber mid, emerald strong.
const scoreColor = (s: number | null) => (s == null ? "#94A3B8" : s >= 60 ? "#059669" : s >= 40 ? "#D97706" : "#E0672E");

export function GoalBanner({ goalText, aiTarget, aiDate, localDate }: {
  goalText?: string; aiTarget: number | null; aiDate?: string | null; localDate?: string | null;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-center gap-6 rounded-[18px] bg-linear-to-br from-ink to-[#1E293B] p-5 px-6 shadow-[0_2px_4px_rgba(15,23,42,0.05),0_12px_32px_-10px_rgba(15,23,42,0.14)]">
      <div className="min-w-[280px] flex-1">
        <div className="mb-[7px] font-mono text-[11px] uppercase tracking-[0.14em] text-sky-300">Your goal</div>
        {goalText ? (
          <div className="text-[15px] leading-relaxed text-slate-200">{goalText}</div>
        ) : (
          <div className="text-[15px] leading-relaxed text-slate-300">Be the accurate, trusted answer when AI assistants describe your business.</div>
        )}
      </div>
      <div className="flex shrink-0 gap-3.5">
        <div className="min-w-[120px] rounded-[12px] border border-white/10 bg-white/[0.07] px-[18px] py-3.5 text-center">
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.06em] text-slate-400">Target AI score</div>
          <div className="font-display text-[26px] font-semibold leading-none tracking-[-0.02em] text-white">
            {aiTarget ?? "—"}<span className="text-[15px] text-slate-400">/100</span>
          </div>
          {aiDate && <div className="mt-[5px] font-mono text-[10px] text-sky-300">by {fmtDate(aiDate)}</div>}
        </div>
        <div className="min-w-[120px] rounded-[12px] border border-white/10 bg-white/[0.07] px-[18px] py-3.5 text-center">
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.06em] text-slate-400">Local SEO</div>
          <div className="font-display text-[26px] font-semibold leading-none tracking-[-0.02em] text-white">Page&nbsp;1</div>
          {localDate && <div className="mt-[5px] font-mono text-[10px] text-sky-300">by {fmtDate(localDate)}</div>}
        </div>
      </div>
    </div>
  );
}

function ScoreGauge({ score }: { score: number | null }) {
  const s = Math.max(0, Math.min(100, score ?? 0));
  const R = 80;
  const C = 2 * Math.PI * R;
  const off = C * (1 - s / 100);
  const col = scoreColor(score);
  return (
    <div className="relative h-[190px] w-[190px] shrink-0">
      <svg width="190" height="190" viewBox="0 0 190 190" className="-rotate-90">
        <circle cx="95" cy="95" r={R} fill="none" stroke="#EEF0F4" strokeWidth="15" />
        <circle cx="95" cy="95" r={R} fill="none" stroke={col} strokeWidth="15" strokeLinecap="round" strokeDasharray={C} strokeDashoffset={off} style={{ transition: "stroke-dashoffset .7s cubic-bezier(0.22,1,0.36,1)" }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="font-display text-[64px] font-semibold leading-[.9] tracking-[-0.02em]" style={{ color: col }}>{score ?? "—"}</div>
        <div className="mt-1 font-mono text-[14px] text-ink-4">/ 100</div>
      </div>
    </div>
  );
}

function worstReason(a: Answer): string {
  if (a.entity_confusion) return "AI describes a different business with your name";
  if (a.awareness === false) return "AI doesn't know your business here";
  if (a.mentions_contested) return "AI raises a concern about you";
  return "AI leans unfavorable here";
}

export function ScoreHero({ score, delta, goalScore, aiDate, aiMonths, worst }: {
  score: number | null; delta?: number | null; goalScore: number | null;
  aiDate?: string | null; aiMonths?: number | null; worst: Answer[];
}) {
  const band = repBand(score);
  const col = scoreColor(score);
  const fillPct = score != null ? Math.max(2, Math.min(100, score)) : 0;
  const gap = score != null && goalScore != null ? Math.max(0, goalScore - score) : null;
  return (
    <section className="mb-5 grid grid-cols-1 gap-5 lg:grid-cols-[1.55fr_1fr]">
      {/* score panel */}
      <div className="relative overflow-hidden rounded-[18px] border border-line bg-card p-7 px-[30px] shadow-[0_1px_2px_rgba(15,23,42,0.04),0_4px_16px_-6px_rgba(15,23,42,0.08)]">
        <div className="flex items-center gap-[30px]">
          <ScoreGauge score={score} />
          <div className="flex flex-1 flex-col gap-[11px]">
            <div className="eyebrow">AI Reputation Score</div>
            <span className="inline-flex items-center gap-1.5 self-start rounded-full px-[11px] py-[5px] font-mono text-[12px] font-semibold uppercase tracking-[0.04em]" style={{ background: `${col}1a`, color: col }}>{band.label}</span>
            {delta != null && Math.abs(delta) >= 0.5 && (
              <span className={`inline-flex items-center gap-1.5 self-start rounded-full px-[11px] py-[5px] font-mono text-[12px] font-semibold uppercase tracking-[0.04em] ${delta >= 0 ? "bg-good-bg text-good" : "bg-alert-bg text-alert"}`}>
                {delta >= 0 ? "▲" : "▼"} {Math.abs(delta)} pts vs last audit
              </span>
            )}
            <div className="text-[14px] leading-relaxed text-ink-3">How favorably AI assistants describe you, averaged across engines. <b className="font-semibold text-ink-2">The indigo marker below is your goal — {goalScore ?? "—"}.</b></div>
          </div>
        </div>
        <div className="mt-6 border-t border-line pt-[22px]">
          <div className="mb-3 flex items-baseline justify-between"><span className="eyebrow">Path to goal</span><span className="font-mono text-[13px] font-semibold text-indigo-strong">GOAL {goalScore ?? "—"}</span></div>
          <div className="relative h-[11px] overflow-hidden rounded-full bg-line">
            <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${fillPct}%`, background: `linear-gradient(90deg, ${col}, #EBA46A)` }} />
            {goalScore != null && <div className="absolute -top-[3px] h-[17px] w-[3px] rounded-[2px] bg-indigo" style={{ left: `${goalScore}%` }} />}
          </div>
          <div className="mt-[9px] flex justify-between font-mono text-[12px] text-ink-4"><span>0</span><span>you · {score ?? "—"}</span><span>100</span></div>
          {aiDate && (
            <div className="mt-4 flex items-center gap-[9px] text-[14px] text-ink-3">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-[15px] w-[15px] text-indigo"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
              <span>On current pace, you reach <b className="font-mono font-semibold text-ink-2">{goalScore}</b> by <b className="font-mono font-semibold text-ink-2">{fmtDate(aiDate)}</b>{aiMonths ? ` — ~${aiMonths} months` : ""}{gap != null ? ` · ${gap} pts to close` : ""}.</span>
            </div>
          )}
        </div>
      </div>

      {/* worst answers */}
      <div className="flex flex-col rounded-[18px] border border-line bg-card p-[22px] shadow-[0_1px_2px_rgba(15,23,42,0.04),0_4px_16px_-6px_rgba(15,23,42,0.08)]">
        <div className="mb-[3px] font-mono text-[11px] uppercase tracking-[0.14em] text-alert">Needs attention · loudest now</div>
        <h2 className="mb-1 font-display text-[18px] font-semibold tracking-[-0.01em] text-ink">What AI says worst about you</h2>
        <div className="mb-3.5 text-[13px] text-ink-3">The answers doing the most damage.</div>
        {worst.length === 0 ? (
          <div className="text-[13px] text-ink-4">No scored answers yet — run an audit.</div>
        ) : (
          worst.slice(0, 2).map((a) => {
            const sc = repScore(a.goal_alignment);
            const snip = (a.answer_text ?? "").slice(0, 120);
            return (
              <div key={a.id} className="mb-2.5 rounded-r-[12px] border-l-[3px] border-alert bg-alert-bg px-3.5 py-3 last:mb-0">
                <div className="mb-[7px] flex items-center gap-2">
                  <span className="rounded-[5px] border border-line-2 bg-white px-[7px] py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.05em] text-ink-2">{engineLabel(a.engine)}</span>
                  {sc != null && <span className="font-mono text-[10px] font-semibold text-alert">{sc}/100 · {worstReason(a)}</span>}
                </div>
                <div className="mb-1.5 text-[14px] font-semibold leading-snug text-ink">“{a.prompt}”</div>
                {snip && <div className="relative pl-[22px] text-[13.5px] italic leading-relaxed text-ink-2 before:absolute before:left-1.5 before:top-0 before:font-semibold before:not-italic before:text-ink-4 before:content-['~']">“{snip}…”</div>}
              </div>
            );
          })
        )}
        <div className="mt-3.5">
          <Link href="/next-steps" className="flex h-[34px] w-full items-center justify-center gap-1.5 rounded-[10px] bg-indigo px-[13px] text-[13.5px] font-semibold text-white shadow-[0_4px_14px_-4px_rgba(79,70,229,0.5)] hover:bg-indigo-strong">Fix these in the plan</Link>
        </div>
      </div>
    </section>
  );
}

function GoalCard({ tone, icon, title, now, target, targetLabel, fillPct, targetMark, date, months }: {
  tone: "score" | "indigo"; icon: ReactNode; title: string; now: string; target: string;
  targetLabel: string; fillPct: number; targetMark: number; date?: string | null; months?: number | null;
}) {
  const grad = tone === "score" ? "linear-gradient(90deg,var(--score),#EBA46A)" : "linear-gradient(90deg,var(--indigo),#7C74F0)";
  return (
    <div className="rounded-[18px] border border-line bg-card p-5 px-6 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_4px_16px_-6px_rgba(15,23,42,0.08)]">
      <div className="mb-4 flex items-center gap-2.5">
        <div className={`grid h-[30px] w-[30px] shrink-0 place-items-center rounded-[9px] ${tone === "score" ? "bg-score-bg text-score" : "bg-indigo-050 text-indigo"}`}>{icon}</div>
        <b className="font-mono text-[12px] font-semibold uppercase tracking-[0.08em] text-ink-3">{title}</b>
      </div>
      <div className="mb-3.5 flex items-baseline gap-3">
        <span className="font-display text-[32px] font-semibold leading-none tracking-[-0.02em]" style={{ color: "var(--score)" }}>{now}</span>
        <span className="text-[18px] text-ink-4">→</span>
        <span className="font-display text-[24px] font-semibold tracking-[-0.02em] text-indigo-strong">{target} <small className="font-mono text-[12px] font-normal text-ink-4">{targetLabel}</small></span>
      </div>
      <div className="relative mb-2.5 h-[9px] overflow-hidden rounded-full bg-line">
        <i className="block h-full rounded-full" style={{ width: `${fillPct}%`, background: grad }} />
        <span className="absolute -top-[3px] h-[15px] w-[3px] rounded-[2px] bg-indigo" style={{ left: `${targetMark}%` }} />
      </div>
      {date && (
        <div className="flex items-center gap-2 text-[14px] text-ink-3">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-[15px] w-[15px] shrink-0 text-indigo"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
          <span>Est. reached <b className="font-mono font-semibold text-ink-2">{fmtDate(date)}</b>{months ? ` · ~${months} months` : ""}</span>
        </div>
      )}
    </div>
  );
}

export function TwoGoals({ score, goalScore, aiDate, aiMonths, localGoal }: {
  score: number | null; goalScore: number | null; aiDate?: string | null; aiMonths?: number | null; localGoal?: LocalSeoGoal;
}) {
  const localNow = localGoal?.current_page_one_rate;
  const localExp = localGoal?.projection?.expected;
  const localPct = localNow != null ? Math.round(localNow * 100) : null;
  return (
    <>
      <div className="mx-0.5 mb-3.5 mt-2 flex items-baseline gap-3">
        <h2 className="font-display text-[21px] font-semibold tracking-[-0.01em] text-ink">Your two goals</h2>
        <span className="text-[14px] text-ink-4">the finish lines everything else is measured against</span>
      </div>
      <div className="mb-[26px] grid grid-cols-1 gap-5 lg:grid-cols-2">
        <GoalCard tone="score"
          icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4"><path d="M12 2l2.4 6.5L21 9l-5 4.5L17.5 21 12 17l-5.5 4L8 13.5 3 9l6.6-.5z" /></svg>}
          title={`AI Reputation · target ${goalScore ?? "—"}`}
          now={String(score ?? "—")} target={String(goalScore ?? "—")} targetLabel="goal"
          fillPct={score != null && goalScore ? Math.round((score / goalScore) * 100) : 0}
          targetMark={100} date={aiDate} months={aiMonths} />
        <GoalCard tone="indigo"
          icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4"><path d="M12 2C8 2 5 5 5 9c0 5 7 13 7 13s7-8 7-13c0-4-3-7-7-7z" /><circle cx="12" cy="9" r="2" /></svg>}
          title="Local SEO · reach page 1"
          now={localPct != null ? `${localPct}%` : "—"} target="Page 1" targetLabel="80% of searches"
          fillPct={localPct != null ? Math.max(2, Math.round((localPct / 80) * 100)) : 2}
          targetMark={100} date={localExp?.target_date} months={localExp?.months ?? null} />
      </div>
    </>
  );
}
