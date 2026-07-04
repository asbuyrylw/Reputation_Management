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
import { useAddWorkOrder } from "@/lib/hooks";

type Json = Record<string, unknown>;
type WeakQuery = { prompt?: string; engine?: string; problem?: string; fix?: string; addressed_by?: string };
type Missing = { topic?: string; asset_type?: string; why?: string };
type Thin = { claim?: string; where_to_get_it?: string };
type LocalGap = { query?: string; current_rank?: unknown; recommendation?: string; why?: string };
type CompGap = { query?: string; competitor?: string; recommendation?: string; why?: string };
type SiteGap = { issue?: string; recommendation?: string; why?: string };

function arr<T>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : [];
}

type WoPayload = {
  title: string; instruction?: string; capability?: string; gap_source?: string;
  source_query?: string; area?: string; why_helps_ai_rep?: string; why_helps_seo?: string;
};

// A real "turn this gap item into a task" button. Idempotent server-side (links to a task the plan
// already made instead of duplicating it) and carries the gap lineage so the task knows why it
// exists and can wire to the content it produces.
function AddTaskButton({ businessId, payload }: { businessId: number | null; payload: WoPayload }) {
  const add = useAddWorkOrder(businessId);
  return (
    <button
      type="button"
      onClick={() => add.mutate(payload)}
      disabled={add.isPending || add.isSuccess}
      className="mt-1.5 inline-flex items-center gap-1 rounded-md border border-indigo-200 bg-indigo-50 px-2 py-1 text-[11px] font-semibold text-indigo-700 transition hover:bg-indigo-100 disabled:opacity-60"
    >
      {add.isSuccess ? "✓ On your task board" : add.isPending ? "Adding…" : "+ Add as task"}
    </button>
  );
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

export function GapsView({
  model,
  asOf,
  verifyButton,
  businessId,
  canEdit,
}: {
  model: Json;
  asOf?: string;
  verifyButton?: ReactNode;
  businessId?: number | null;
  canEdit?: boolean;
}) {
  const addBtn = (payload: WoPayload) =>
    canEdit && businessId != null ? <AddTaskButton businessId={businessId} payload={payload} /> : null;
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
          <Chip n={weak.length} label="questions AI gets wrong" tone="bad" targetId="gap-weak" />
          <Chip n={missing.length} label="pages to create" tone="neutral" targetId="gap-missing" />
          <Chip n={thin.length} label="claims needing proof" tone="neutral" targetId="gap-thin" />
          {localSeo.length > 0 && <Chip n={localSeo.length} label="local searches to win" tone="neutral" targetId="gap-local" />}
          {compDef.length > 0 && <Chip n={compDef.length} label="questions rivals win" tone="bad" targetId="gap-competitor" />}
          {siteTech.length > 0 && <Chip n={siteTech.length} label="website fixes" tone="neutral" targetId="gap-site" />}
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
      <div id="gap-weak" className="scroll-mt-24">
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
              {w.fix && (
                <div className="ml-6 mt-1.5 rounded-md bg-emerald-50 px-2 py-1.5 text-sm text-slate-700 ring-1 ring-inset ring-emerald-200">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-emerald-700">The fix</span>
                  <div className="mt-0.5">{w.fix}</div>
                </div>
              )}
              {w.engine && <div className="mt-0.5 pl-6 text-xs text-slate-400">Seen on {engineLabel(w.engine)}</div>}
              <div className="ml-6">{addBtn({ title: `Improve AI answer: "${(w.prompt || "").slice(0, 70)}"`, instruction: w.fix || w.problem, capability: "content_writing", gap_source: "audited gap: weak answer", source_query: w.prompt, why_helps_ai_rep: w.fix })}</div>
            </li>
          ))}
        </ul>
      </DataSection>
      </div>

      {/* pages to create */}
      <div id="gap-missing" className="scroll-mt-24">
      <DataSection
        title="Pages to create"
        severity={missing.length > 0 ? "med" : "good"}
        headline={`${missing.length} pages on your own site would give AI accurate facts to quote about you. Each note below says exactly what to put in it.`}
        highlights={[{ label: "Pages", value: String(missing.length) }]}
        action={{ label: "Open task board", href: "/content/work-orders" }}
        detailsLabel="See the pages + what goes in them"
      >
        <ul className="space-y-3">
          {missing.map((m, i) => (
            <li key={i} className="rounded-lg border border-slate-100 p-3">
              <div className="text-sm font-semibold text-slate-800">{m.topic}</div>
              {m.asset_type && <div className="text-xs text-slate-400">{m.asset_type}</div>}
              {m.why && <div className="mt-1 text-sm text-slate-600"><span className="font-medium">What goes in it: </span>{m.why}</div>}
              {addBtn({ title: `Create owned asset: ${m.topic}`, instruction: `Produce a ${m.asset_type || "article"} on '${m.topic}'. ${m.why || ""}`.trim(), capability: (m.asset_type || "").toLowerCase().includes("video") ? "video_creation" : "content_writing", gap_source: "audited gap: missing owned content", source_query: m.topic, area: "content", why_helps_ai_rep: m.why })}
            </li>
          ))}
        </ul>
      </DataSection>
      </div>

      {/* claims needing proof */}
      <div id="gap-thin" className="scroll-mt-24">
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
                {addBtn({ title: `Corroborate: ${t.claim}`, instruction: `Secure third-party coverage supporting '${t.claim}'. Source: ${t.where_to_get_it || ""}`.trim(), capability: "press_outreach", gap_source: "audited gap: thin corroboration", source_query: t.claim })}
              </li>
            );
          })}
        </ul>
      </DataSection>
      </div>

      {/* local searches not on page 1 (from live Google rankings) */}
      {localSeo.length > 0 && (
        <div id="gap-local" className="scroll-mt-24">
        <DataSection
          title="Local searches to win"
          severity="med"
          headline={`${localSeo.length} local searches your neighbors type where you're not yet on Google's first page. Each becomes a local-SEO task.`}
          highlights={[{ label: "Searches", value: String(localSeo.length) }]}
          action={{ label: "Open task board", href: "/content/work-orders" }}
          detailsLabel="See the searches + what to do"
        >
          <ul className="space-y-3">
            {localSeo.map((g, i) => (
              <li key={i} className="rounded-lg border border-slate-100 p-3">
                <div className="text-sm font-semibold text-slate-800">“{g.query}”</div>
                {g.current_rank != null && <div className="text-xs text-slate-400">Current position: {String(g.current_rank)}</div>}
                {g.recommendation && <div className="mt-1 text-sm text-slate-600">{g.recommendation}</div>}
                {g.why && <div className="mt-0.5 text-xs text-slate-500">{g.why}</div>}
                {addBtn({ title: `Reach page 1 for '${g.query}'`, instruction: `${g.recommendation || ""} Current position: ${g.current_rank != null ? String(g.current_rank) : "off page 1"}.`.trim(), capability: "local_content_creation", gap_source: "local search ranking", source_query: g.query, area: "local", why_helps_seo: g.why })}
              </li>
            ))}
          </ul>
        </DataSection>
        </div>
      )}

      {/* questions where a competitor appears and you don't */}
      {compDef.length > 0 && (
        <div id="gap-competitor" className="scroll-mt-24">
        <DataSection
          title="Questions your rivals win"
          severity={compDef.length > 3 ? "high" : "med"}
          headline={`${compDef.length} questions where a competitor shows up in AI answers and you don't. Close these to take back the conversation.`}
          highlights={[{ label: "Questions", value: String(compDef.length), tone: "bad" }]}
          action={{ label: "Open task board", href: "/content/work-orders" }}
          detailsLabel="See the questions + how to compete"
        >
          <ul className="space-y-3">
            {compDef.map((g, i) => (
              <li key={i} className="rounded-lg border border-slate-100 p-3">
                <div className="text-sm font-semibold text-slate-800">“{g.query}”</div>
                {g.competitor && <div className="text-xs text-rose-600">A rival wins here: {g.competitor}</div>}
                {g.recommendation && <div className="mt-1 text-sm text-slate-600">{g.recommendation}</div>}
                {g.why && <div className="mt-0.5 text-xs text-slate-500">{g.why}</div>}
                {addBtn({ title: `Compete for '${g.query}'`, instruction: `${g.recommendation || ""} A competitor (${g.competitor || "a rival"}) appears here and you don't.`.trim(), capability: "content_writing", gap_source: "competitor analysis", source_query: g.query, area: "content", why_helps_ai_rep: g.why })}
              </li>
            ))}
          </ul>
        </DataSection>
        </div>
      )}

      {/* on-site technical issues that limit AI extraction */}
      {siteTech.length > 0 && (
        <div id="gap-site" className="scroll-mt-24">
        <DataSection
          title="Website fixes"
          severity="med"
          headline={`${siteTech.length} fixes on your own site that would help AI read and trust your facts (thin/missing pages, schema, weak coverage).`}
          highlights={[{ label: "Fixes", value: String(siteTech.length) }]}
          action={{ label: "Open task board", href: "/content/work-orders" }}
          detailsLabel="See the fixes"
        >
          <ul className="space-y-3">
            {siteTech.map((g, i) => (
              <li key={i} className="rounded-lg border border-slate-100 p-3">
                <div className="text-sm font-semibold text-slate-800">{g.issue}</div>
                {g.recommendation && <div className="mt-1 text-sm text-slate-600">{g.recommendation}</div>}
                {g.why && <div className="mt-0.5 text-xs text-slate-500">{g.why}</div>}
                {addBtn({ title: `Fix site: ${g.issue}`, instruction: g.recommendation, capability: /schema/i.test(`${g.issue} ${g.recommendation || ""}`) ? "schema_markup" : "content_writing", gap_source: "site crawl", area: "website", why_helps_seo: g.why })}
              </li>
            ))}
          </ul>
        </DataSection>
        </div>
      )}

      {/* recommended social presence — now a compact pointer; the Social page is the source of
          truth for per-platform presence, completeness, recommendations, and the social tasks. */}
      {surfaceEntries.length > 0 && (
        <Card>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-sm font-semibold text-slate-900">Social presence</div>
              <p className="mt-0.5 text-sm text-slate-600">
                Best-practice actions across{" "}
                <span className="font-semibold">{surfaceEntries.length}</span>{" "}
                platform{surfaceEntries.length === 1 ? "" : "s"} ({surfaceEntries.map(([p]) => PLATFORM_LABEL[p] ?? p.replace(/_/g, " ")).join(", ")}).
                See which profiles exist, how complete they are, and what to improve — plus your social tasks — on the Social page.
              </p>
            </div>
            {verifyButton}
          </div>
          <Link
            href="/social"
            className="mt-3 inline-block rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            Manage your social presence on the Social page →
          </Link>
        </Card>
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
        <ul className="list-disc space-y-1.5 pl-6 text-sm text-slate-600">
          {schema.map((g, i) => (
            <li key={i}>{g} {addBtn({ title: `Add schema: ${g}`, instruction: `Generate and deploy JSON-LD (${g}) on the relevant pages so answer engines can cleanly extract your facts.`, capability: "schema_markup", gap_source: "audited gap: schema", source_query: g, area: "website" })}</li>
          ))}
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

// UX-2: clicking a tally scrolls to its section below. scroll-mt on the anchor keeps the section
// header clear of the sticky top bar.
function scrollToSection(id: string) {
  if (typeof document === "undefined") return;
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function Chip({ n, label, tone = "neutral", targetId }: { n: number; label: string; tone?: "bad" | "neutral" | "good"; targetId?: string }) {
  const c = tone === "bad" && n > 0 ? "bg-rose-50 text-rose-700 border-rose-200" : "bg-slate-100 text-slate-700 border-slate-200";
  const inner = <><span className="font-semibold">{n}</span> {label}</>;
  // Only make it a jump-button when the section actually renders (n > 0 for the conditional ones;
  // the always-rendered sections still jump even at 0 so the tally stays consistent).
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
  return (
    <span className={`rounded-lg border px-2.5 py-1 text-sm ${c}`}>{inner}</span>
  );
}
