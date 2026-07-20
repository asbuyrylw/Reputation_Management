"use client";

// Gap Analysis = a REPORT ONLY. It says what's wrong, where it shows, and what it costs you —
// grouped into the three areas AI Visibility / SEO (on-site) / Search (rankings). It does NOT say
// how to fix anything and has no task buttons: the fix, the approach, and the tasks all live on
// the Strategy page (each section here links straight to its strategy). This keeps "diagnosis"
// and "plan" cleanly separated.

import type { ReactNode } from "react";
import Link from "next/link";
import { Card } from "./ui";
import { DataSection } from "./primitives";
import { Term } from "./Term";
import { engineLabel } from "@/lib/engines";

type Json = Record<string, unknown>;
type WeakQuery = { prompt?: string; engine?: string; problem?: string };
type Missing = { topic?: string; asset_type?: string; why?: string };
type Thin = { claim?: string };
type LocalGap = { query?: string; current_rank?: unknown };
type CompGap = { query?: string; competitor?: string };
type SiteGap = { issue?: string };

function arr<T>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : [];
}

// A section-group header for the three gap areas, each linking to its plan on the Strategy page.
function GroupHead({ title, note, strategyHref }: { title: string; note?: string; strategyHref: string }) {
  return (
    <div className="mt-7 mb-1 flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1 border-b border-slate-200 pb-1">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <h3 className="text-[13px] font-bold uppercase tracking-wide text-slate-700">{title}</h3>
        {note && <span className="text-[11px] text-slate-400">{note}</span>}
      </div>
      <Link href={strategyHref} className="text-[11.5px] font-semibold text-indigo-600 hover:text-indigo-700 hover:underline">
        See the plan to close these →
      </Link>
    </div>
  );
}

// Split prose that embeds "(1) … (2) …" into a lead sentence + numbered items (used for the summary).
function splitNumbered(text: string): { lead: string; items: string[] } {
  const t = (text || "").trim();
  if (!/\(\d+\)|(?:^|\s)\d+[.)]\s/.test(t)) return { lead: t, items: [] };
  const parts = t.split(/\s*\(\d+\)\s*|(?:^|\s)\d+[.)]\s+/);
  const lead = (parts.shift() || "").trim().replace(/[—:,;-]\s*$/, "");
  const items = parts.map((s) => s.trim().replace(/;$/, "")).filter(Boolean);
  if (items.length < 2) return { lead: t, items: [] };
  return { lead, items };
}

function readinessTone(n: number): string {
  if (n >= 60) return "text-emerald-700";
  if (n >= 40) return "text-amber-700";
  return "text-rose-700";
}

export function GapsView({ model, asOf, verifyButton }: {
  model: Json;
  asOf?: string;
  verifyButton?: ReactNode;
}) {
  const summary = (model.summary as string) || "";
  const weak = arr<WeakQuery>(model.weak_queries);
  const missing = arr<Missing>(model.missing_owned_content);
  const thin = arr<Thin>(model.thin_corroboration);
  const schema = arr<string>(model.schema_gaps);
  const localSeo = arr<LocalGap>(model.local_seo_gaps);
  const compDef = arr<CompGap>(model.competitor_defense);
  const siteTech = arr<SiteGap>(model.site_technical_gaps);
  const readiness = model.avg_semantic_readiness as number | undefined;
  const sum = splitNumbered(summary);

  return (
    <div className="space-y-4">
      {/* scorecard */}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="text-sm font-semibold text-slate-900">What the audit found</div>
          {verifyButton}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Chip n={weak.length} label="questions AI gets wrong" tone="bad" targetId="gap-weak" />
          <Chip n={missing.length} label="pages missing" tone="neutral" targetId="gap-missing" />
          <Chip n={thin.length} label="claims needing proof" tone="neutral" targetId="gap-thin" />
          {compDef.length > 0 && <Chip n={compDef.length} label="questions rivals win" tone="bad" targetId="gap-competitor" />}
          {siteTech.length > 0 && <Chip n={siteTech.length} label="website issues" tone="neutral" targetId="gap-site" />}
          {schema.length > 0 && <Chip n={schema.length} label="schema types missing" tone="neutral" targetId="gap-schema" />}
          {localSeo.length > 0 && <Chip n={localSeo.length} label="local searches to win" tone="neutral" targetId="gap-local" />}
        </div>
        {summary && (
          <div className="mt-3 rounded-lg border border-indigo-100 bg-indigo-050/60 p-3.5 text-sm leading-relaxed text-slate-700">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-indigo-strong">The situation</div>
            {sum.lead && <p>{sum.lead}{sum.items.length ? ":" : ""}</p>}
            {sum.items.length > 0 && (
              <ol className="mt-1 list-decimal space-y-1 pl-6">
                {sum.items.map((it, i) => <li key={i}>{it}</li>)}
              </ol>
            )}
          </div>
        )}
        <p className="mt-3 text-xs text-slate-400">
          This is the diagnosis — what&apos;s wrong and what it costs you. {asOf ? `Based on the audit from ${asOf}. ` : ""}
          Head to <Link href="/strategy" className="font-medium text-indigo-600 hover:underline">Strategy</Link> for exactly how each of these gets closed.
        </p>
      </Card>

      {/* ============================ AI VISIBILITY ============================ */}
      <GroupHead title="AI Visibility" note="how AI assistants answer about you" strategyHref="/strategy#ai_visibility" />

      <div id="gap-weak" className="scroll-mt-24">
      <DataSection
        title="Questions where AI fails you"
        severity={weak.length > 5 ? "high" : weak.length > 0 ? "med" : "good"}
        headline={
          weak.length
            ? `AI gives a weak, wrong, or unfavorable answer to ${weak.length} common questions buyers ask about you — where you're losing trust.`
            : "AI answers the common questions about you reasonably well."
        }
        highlights={[{ label: "Questions", value: String(weak.length), tone: weak.length ? "bad" : "good" }]}
        defaultOpen
        detailsLabel="See the questions"
      >
        <ul className="space-y-3">
          {weak.map((w, i) => (
            <li key={i}>
              <div className="text-sm font-semibold text-slate-800">“{w.prompt}”</div>
              {w.problem && (
                <ul className="mt-1 list-disc space-y-0.5 pl-6 text-sm text-slate-600">
                  {w.problem.split(/;\s+/).filter(Boolean).map((p, j) => <li key={j}>{p}</li>)}
                </ul>
              )}
              {w.engine && <div className="mt-0.5 pl-6 text-xs text-slate-400">Seen on {engineLabel(w.engine)}</div>}
            </li>
          ))}
        </ul>
      </DataSection>
      </div>

      <div id="gap-missing" className="scroll-mt-24">
      <DataSection
        title="Pages you're missing"
        severity={missing.length > 0 ? "med" : "good"}
        headline={`${missing.length} topics have no page on your own site, so AI has no accurate facts of yours to quote about them.`}
        highlights={[{ label: "Topics", value: String(missing.length) }]}
        detailsLabel="See the topics"
      >
        <ul className="space-y-2">
          {missing.map((m, i) => (
            <li key={i} className="rounded-lg border border-slate-100 p-3">
              <div className="text-sm font-semibold text-slate-800">{m.topic}</div>
              {m.asset_type && <div className="text-xs text-slate-400">No {m.asset_type} exists yet</div>}
            </li>
          ))}
        </ul>
      </DataSection>
      </div>

      <div id="gap-thin" className="scroll-mt-24">
      <DataSection
        title="Claims AI won't trust yet"
        severity={thin.length > 0 ? "med" : "good"}
        headline={`AI trusts outside proof, not self-claims. ${thin.length} of your claims have no third-party source, so AI won't repeat them confidently.`}
        highlights={[{ label: "Claims", value: String(thin.length) }]}
        detailsLabel="See the claims"
      >
        <ul className="space-y-2">
          {thin.map((t, i) => (
            <li key={i} className="text-sm text-slate-700">{t.claim}</li>
          ))}
        </ul>
      </DataSection>
      </div>

      {compDef.length > 0 && (
        <div id="gap-competitor" className="scroll-mt-24">
        <DataSection
          title="Questions your rivals win"
          severity={compDef.length > 3 ? "high" : "med"}
          headline={`${compDef.length} questions where a competitor shows up in AI answers and you don't.`}
          highlights={[{ label: "Questions", value: String(compDef.length), tone: "bad" }]}
          detailsLabel="See the questions"
        >
          <ul className="space-y-2">
            {compDef.map((g, i) => (
              <li key={i} className="rounded-lg border border-slate-100 p-3">
                <div className="text-sm font-semibold text-slate-800">“{g.query}”</div>
                {g.competitor && <div className="text-xs text-rose-600">A rival wins here: {g.competitor}</div>}
              </li>
            ))}
          </ul>
        </DataSection>
        </div>
      )}

      {/* ============================ SEO (ON-SITE) ============================ */}
      <GroupHead title="SEO (on-site)" note="how cleanly your site can be read" strategyHref="/strategy#seo" />

      {siteTech.length > 0 && (
        <div id="gap-site" className="scroll-mt-24">
        <DataSection
          title="Website issues"
          severity="med"
          headline={`${siteTech.length} on-site issues (thin/missing pages, weak coverage) that limit how well AI can read and trust your facts.`}
          highlights={[{ label: "Issues", value: String(siteTech.length) }]}
          detailsLabel="See the issues"
        >
          <ul className="space-y-2">
            {siteTech.map((g, i) => (
              <li key={i} className="rounded-lg border border-slate-100 p-3 text-sm font-semibold text-slate-800">{g.issue}</li>
            ))}
          </ul>
        </DataSection>
        </div>
      )}

      <div id="gap-schema" className="scroll-mt-24">
      <DataSection
        title="Structured data (schema)"
        severity={schema.length > 0 ? "low" : "good"}
        headline={`${schema.length} hidden code labels are missing that help AI read your site's official facts correctly.`}
        highlights={[{ label: "Missing", value: String(schema.length) }]}
        detailsLabel="See the technical gaps"
      >
        <p className="mb-2 text-sm text-slate-600">
          <Term name="schema">Schema</Term> is hidden labels in your site&apos;s code that spell out your
          official name, reviews, and FAQs so AI reads them correctly. These {schema.length} are missing.
        </p>
        <ul className="list-disc space-y-1 pl-6 text-sm text-slate-600">
          {schema.map((g, i) => <li key={i}>{g}</li>)}
        </ul>
      </DataSection>
      </div>

      {typeof readiness === "number" && (
        <Card>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-slate-700">
            <Term name="semantic readiness"><span className="font-medium text-slate-900">Site readiness for AI</span></Term>
            <span className={`text-base font-bold ${readinessTone(Math.round(readiness))}`}>{Math.round(readiness)}/100</span>
            <span className="text-slate-600">— how easily AI can pull a clean answer from your pages (healthy sites score 60+).</span>
          </div>
          <Link href="/seo" className="mt-2 inline-block rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700">
            See your website report →
          </Link>
        </Card>
      )}

      {/* ============================ SEARCH (RANKINGS) ============================ */}
      {localSeo.length > 0 && (
        <>
        <GroupHead title="Search (rankings)" note="where you land on Google" strategyHref="/strategy#search" />
        <div id="gap-local" className="scroll-mt-24">
        <DataSection
          title="Local searches you're not winning"
          severity="med"
          headline={`${localSeo.length} local searches your neighbors type where you're not yet on Google's first page.`}
          highlights={[{ label: "Searches", value: String(localSeo.length) }]}
          detailsLabel="See the searches"
        >
          <ul className="space-y-2">
            {localSeo.map((g, i) => (
              <li key={i} className="rounded-lg border border-slate-100 p-3">
                <div className="text-sm font-semibold text-slate-800">“{g.query}”</div>
                {g.current_rank != null && <div className="text-xs text-slate-400">Current position: {String(g.current_rank)}</div>}
              </li>
            ))}
          </ul>
        </DataSection>
        </div>
        </>
      )}
    </div>
  );
}

// Clicking a tally scrolls to its section. scroll-mt on the anchor keeps the header clear of the top bar.
function scrollToSection(id: string) {
  if (typeof document === "undefined") return;
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function Chip({ n, label, tone = "neutral", targetId }: { n: number; label: string; tone?: "bad" | "neutral" | "good"; targetId?: string }) {
  const c = tone === "bad" && n > 0 ? "bg-rose-50 text-rose-700 border-rose-200" : "bg-slate-100 text-slate-700 border-slate-200";
  const inner = <><span className="font-semibold">{n}</span> {label}</>;
  if (targetId) {
    return (
      <button
        type="button"
        onClick={() => scrollToSection(targetId)}
        className={`group rounded-lg border px-2.5 py-1 text-sm transition hover:ring-2 hover:ring-indigo-300 ${c}`}
        title="Jump to this section"
      >
        {inner} <span aria-hidden className="text-slate-400 group-hover:text-indigo-500">↓</span>
      </button>
    );
  }
  return <span className={`rounded-lg border px-2.5 py-1 text-sm ${c}`}>{inner}</span>;
}
