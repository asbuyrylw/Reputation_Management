"use client";

// Purpose-built replacement for the generic DataBlocks dump on the Gaps page. Leads with a
// scorecard + plain-English "what this means", then each category is a scannable, scored
// DataSection (highlight first, details on click) — and the action-bearing ones link to the
// work orders / content the same gap model already produces.

import type { ReactNode } from "react";
import Link from "next/link";
import { Card } from "./ui";
import { DataSection } from "./primitives";
import { Term } from "./Term";
import { engineLabel } from "@/lib/engines";

type Json = Record<string, unknown>;
type WeakQuery = { prompt?: string; engine?: string; problem?: string };
type Missing = { topic?: string; asset_type?: string; why?: string };
type Thin = { claim?: string; where_to_get_it?: string };
type LocalGap = { query?: string; current_rank?: unknown; recommendation?: string; why?: string };
type CompGap = { query?: string; competitor?: string; recommendation?: string; why?: string };
type SiteGap = { issue?: string; recommendation?: string; why?: string };

function arr<T>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : [];
}

// Split prose that embeds "(1) … (2) …" (or "1. … 2. …") into a lead sentence + the
// numbered items, so a wall of text becomes an indented list.
function splitNumbered(text: string): { lead: string; items: string[] } {
  const t = (text || "").trim();
  if (!/\(\d+\)|(?:^|\s)\d+[.)]\s/.test(t)) return { lead: t, items: [] };
  const parts = t.split(/\s*\(\d+\)\s*|(?:^|\s)\d+[.)]\s+/);
  const lead = (parts.shift() || "").trim().replace(/[—:,;-]\s*$/, "");
  const items = parts.map((s) => s.trim().replace(/;$/, "")).filter(Boolean);
  if (items.length < 2) return { lead: t, items: [] };
  return { lead, items };
}

// A surface-action line: bold a short "label:" prefix; otherwise show plain.
function ActionItem({ text }: { text: string }) {
  const i = text.indexOf(": ");
  if (i > 0 && i <= 48) {
    return (
      <li>
        <span className="font-semibold text-slate-800">{text.slice(0, i)}:</span> {text.slice(i + 2)}
      </li>
    );
  }
  return <li>{text}</li>;
}

const PLATFORM_LABEL: Record<string, string> = {
  x: "X/Twitter",
  google_business: "Google Business",
  reddit: "Reddit",
  linkedin: "LinkedIn",
  facebook: "Facebook",
};

// Strip a leading "N_" / "N." and the underscores from a priority-order code -> normal text.
function cleanStep(s: string): string {
  return (s || "")
    .replace(/^\d+[_\s.)-]+/, "")
    .replace(/_/g, " ")
    .replace(/^\w/, (c) => c.toUpperCase());
}

function readinessTone(n: number): string {
  if (n >= 60) return "text-emerald-700";
  if (n >= 40) return "text-amber-700";
  return "text-rose-700";
}

type Presence = Record<string, { exists: boolean | null; profile_url: string | null; confidence: string | null }>;

export function GapsView({
  model,
  asOf,
  socialPresence,
  verifyButton,
}: {
  model: Json;
  asOf?: string;
  socialPresence?: Presence;
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
  const priority = arr<string>(model.priority_order);
  const surface = (model.surface_actions as Record<string, unknown>) || {};
  const surfaceEntries = Object.entries(surface).filter(([, v]) => arr<string>(v).length > 0);
  const readiness = model.avg_semantic_readiness as number | undefined;
  const sum = splitNumbered(summary);

  return (
    <div className="space-y-4">
      {/* scorecard */}
      <Card>
        <div className="text-sm font-semibold text-slate-900">What the audit found</div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Chip n={weak.length} label="questions AI gets wrong" tone="bad" />
          <Chip n={missing.length} label="pages to create" tone="neutral" />
          <Chip n={thin.length} label="claims needing proof" tone="neutral" />
          <Chip n={localSeo.length} label="local searches to win" tone="neutral" />
          <Chip n={compDef.length} label="questions rivals win" tone="bad" />
          <Chip n={siteTech.length} label="website fixes" tone="neutral" />
        </div>
        {summary && (
          <details className="mt-3">
            <summary className="cursor-pointer text-sm font-medium text-slate-500 hover:text-slate-800">
              ▸ Read the full summary
            </summary>
            <div className="mt-2 text-sm leading-relaxed text-slate-700">
              {sum.lead && <p>{sum.lead}{sum.items.length ? ":" : ""}</p>}
              {sum.items.length > 0 && (
                <ol className="mt-1 list-decimal space-y-1 pl-6">
                  {sum.items.map((it, i) => <li key={i}>{it}</li>)}
                </ol>
              )}
            </div>
          </details>
        )}
        <p className="mt-3 text-xs text-slate-400">
          Each item below links to the work it creates. {asOf ? `Based on the audit from ${asOf}.` : ""} Recheck after your next audit.
        </p>
      </Card>

      {/* questions AI fails */}
      <DataSection
        title="Questions where AI fails you"
        severity={weak.length > 5 ? "high" : weak.length > 0 ? "med" : "good"}
        headline={
          weak.length
            ? `AI gives a weak, wrong, or unfavorable answer to ${weak.length} common questions buyers ask about you. These are where you're losing trust.`
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

      {/* pages to create */}
      <DataSection
        title="Pages to create"
        severity={missing.length > 0 ? "med" : "good"}
        headline={`${missing.length} pages on your own site would give AI accurate facts to quote about you. Each note below says exactly what to put in it.`}
        highlights={[{ label: "Pages", value: String(missing.length) }]}
        action={{ label: "Turn into tasks", href: "/content/work-orders" }}
        detailsLabel="See the pages + what goes in them"
      >
        <ul className="space-y-3">
          {missing.map((m, i) => (
            <li key={i} className="rounded-lg border border-slate-100 p-3">
              <div className="text-sm font-semibold text-slate-800">{m.topic}</div>
              {m.asset_type && <div className="text-xs text-slate-400">{m.asset_type}</div>}
              {m.why && <div className="mt-1 text-sm text-slate-600"><span className="font-medium">What goes in it: </span>{m.why}</div>}
            </li>
          ))}
        </ul>
      </DataSection>

      {/* claims needing proof */}
      <DataSection
        title="Claims AI won't trust yet"
        severity={thin.length > 0 ? "med" : "good"}
        headline={`AI trusts outside proof, not self-claims. ${thin.length} of your claims need a third-party source before AI will repeat them confidently.`}
        highlights={[{ label: "Claims", value: String(thin.length) }]}
        detailsLabel="See the claims + where to get proof"
      >
        <ul className="space-y-3">
          {thin.map((t, i) => {
            const proof = splitNumbered(t.where_to_get_it || "");
            return (
              <li key={i}>
                <div className="text-sm font-semibold text-slate-800">{t.claim}</div>
                {t.where_to_get_it && (
                  <div className="mt-1 pl-6">
                    <div className="text-xs font-medium uppercase tracking-wide text-slate-400">Where to get proof</div>
                    <ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-sm text-slate-600">
                      {proof.items.length > 0
                        ? proof.items.map((it, j) => <li key={j}>{it}</li>)
                        : <li>{t.where_to_get_it}</li>}
                    </ul>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </DataSection>

      {/* local searches not on page 1 (from live Google rankings) */}
      {localSeo.length > 0 && (
        <DataSection
          title="Local searches to win"
          severity="med"
          headline={`${localSeo.length} local searches your neighbors type where you're not yet on Google's first page. Each becomes a local-SEO task.`}
          highlights={[{ label: "Searches", value: String(localSeo.length) }]}
          action={{ label: "Turn into tasks", href: "/content/work-orders" }}
          detailsLabel="See the searches + what to do"
        >
          <ul className="space-y-3">
            {localSeo.map((g, i) => (
              <li key={i} className="rounded-lg border border-slate-100 p-3">
                <div className="text-sm font-semibold text-slate-800">“{g.query}”</div>
                {g.current_rank != null && <div className="text-xs text-slate-400">Current position: {String(g.current_rank)}</div>}
                {g.recommendation && <div className="mt-1 text-sm text-slate-600">{g.recommendation}</div>}
                {g.why && <div className="mt-0.5 text-xs text-slate-500">{g.why}</div>}
              </li>
            ))}
          </ul>
        </DataSection>
      )}

      {/* questions where a competitor appears and you don't */}
      {compDef.length > 0 && (
        <DataSection
          title="Questions your rivals win"
          severity={compDef.length > 3 ? "high" : "med"}
          headline={`${compDef.length} questions where a competitor shows up in AI answers and you don't. Close these to take back the conversation.`}
          highlights={[{ label: "Questions", value: String(compDef.length), tone: "bad" }]}
          action={{ label: "Turn into tasks", href: "/content/work-orders" }}
          detailsLabel="See the questions + how to compete"
        >
          <ul className="space-y-3">
            {compDef.map((g, i) => (
              <li key={i} className="rounded-lg border border-slate-100 p-3">
                <div className="text-sm font-semibold text-slate-800">“{g.query}”</div>
                {g.competitor && <div className="text-xs text-rose-600">A rival wins here: {g.competitor}</div>}
                {g.recommendation && <div className="mt-1 text-sm text-slate-600">{g.recommendation}</div>}
                {g.why && <div className="mt-0.5 text-xs text-slate-500">{g.why}</div>}
              </li>
            ))}
          </ul>
        </DataSection>
      )}

      {/* on-site technical issues that limit AI extraction */}
      {siteTech.length > 0 && (
        <DataSection
          title="Website fixes"
          severity="med"
          headline={`${siteTech.length} fixes on your own site that would help AI read and trust your facts (thin/missing pages, schema, weak coverage).`}
          highlights={[{ label: "Fixes", value: String(siteTech.length) }]}
          action={{ label: "Turn into tasks", href: "/content/work-orders" }}
          detailsLabel="See the fixes"
        >
          <ul className="space-y-3">
            {siteTech.map((g, i) => (
              <li key={i} className="rounded-lg border border-slate-100 p-3">
                <div className="text-sm font-semibold text-slate-800">{g.issue}</div>
                {g.recommendation && <div className="mt-1 text-sm text-slate-600">{g.recommendation}</div>}
                {g.why && <div className="mt-0.5 text-xs text-slate-500">{g.why}</div>}
              </li>
            ))}
          </ul>
        </DataSection>
      )}

      {/* recommended social presence (NOT verified gaps) */}
      {surfaceEntries.length > 0 && (
        <DataSection
          title="Recommended social presence"
          severity="low"
          headline="Best-practice actions to build accurate presence on the platforms AI reads — grouped by platform."
          highlights={[{ label: "Platforms", value: String(surfaceEntries.length) }]}
          detailsLabel="See the recommendations by platform"
        >
          <div className="mb-3 flex flex-wrap items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            <span className="mt-0.5 rounded bg-amber-200 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-900">
              Recommendation
            </span>
            <span className="min-w-0 flex-1">
              These are best-practice suggestions, <span className="font-semibold">not confirmed gaps</span> — treat each as
              “create or improve.” Use <span className="font-semibold">Check my profiles</span> to confirm which already exist.
            </span>
            {verifyButton}
          </div>
          <div className="space-y-4">
            {surfaceEntries.map(([platform, actions]) => {
              const p = socialPresence?.[platform];
              return (
                <div key={platform}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-slate-900">{PLATFORM_LABEL[platform] ?? platform.replace(/_/g, " ")}</span>
                    {p?.exists === true && p.profile_url && (
                      <a href={p.profile_url} target="_blank" rel="noreferrer" className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] text-emerald-700 hover:underline">
                        profile found — improve it ↗
                      </a>
                    )}
                    {p?.exists === false && (
                      <span className="rounded-full bg-rose-50 px-2 py-0.5 text-[10px] text-rose-700">no profile found — create one</span>
                    )}
                    {p && <span className="text-[10px] text-slate-400">({p.confidence} check)</span>}
                  </div>
                  <ul className="mt-1 list-disc space-y-1 pl-6 text-sm text-slate-600">
                    {arr<string>(actions).map((a, i) => <ActionItem key={i} text={a} />)}
                  </ul>
                </div>
              );
            })}
          </div>
        </DataSection>
      )}

      {/* schema / structured data */}
      <DataSection
        title="Structured data (schema)"
        severity={schema.length > 0 ? "low" : "good"}
        headline={`${schema.length} hidden code labels are missing that help AI read your site's official facts correctly. This is a developer task.`}
        highlights={[{ label: "Gaps", value: String(schema.length) }]}
        detailsLabel="See the technical gaps"
      >
        <p className="mb-2 text-sm text-slate-600">
          <Term name="schema">Schema</Term> is hidden labels in your site&apos;s code that spell out your
          official name, reviews, and FAQs so AI reads them correctly. These {schema.length} are missing —
          a developer task.
        </p>
        <ul className="list-disc space-y-1 pl-6 text-sm text-slate-600">
          {schema.map((g, i) => <li key={i}>{g}</li>)}
        </ul>
      </DataSection>

      {/* priority order */}
      {priority.length > 0 && (
        <DataSection
          title="Recommended order"
          severity="low"
          headline="The order to tackle the work for the fastest score improvement. These become your tracked tasks."
          highlights={[{ label: "Steps", value: String(priority.length) }]}
          action={{ label: "Open your task list", href: "/content/work-orders" }}
          detailsLabel="See the order"
        >
          <ol className="list-decimal space-y-1.5 pl-6 text-sm text-slate-700">
            {priority.map((p, i) => <li key={i}>{cleanStep(p)}</li>)}
          </ol>
        </DataSection>
      )}

      {typeof readiness === "number" && (
        <Card>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-slate-700">
            <Term name="semantic readiness"><span className="font-medium text-slate-900">Site readiness for AI</span></Term>
            <span className={`text-base font-bold ${readinessTone(Math.round(readiness))}`}>{Math.round(readiness)}/100</span>
            <span className="text-slate-600">— how easily AI can pull a clean answer from your pages (healthy sites score 60+).</span>
          </div>
          <Link
            href="/seo"
            className="mt-2 inline-block rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            See your website report →
          </Link>
        </Card>
      )}
    </div>
  );
}

function Chip({ n, label, tone = "neutral" }: { n: number; label: string; tone?: "bad" | "neutral" | "good" }) {
  const c = tone === "bad" && n > 0 ? "bg-rose-50 text-rose-700 border-rose-200" : "bg-slate-100 text-slate-700 border-slate-200";
  return (
    <span className={`rounded-lg border px-2.5 py-1 text-sm ${c}`}>
      <span className="font-semibold">{n}</span> {label}
    </span>
  );
}
