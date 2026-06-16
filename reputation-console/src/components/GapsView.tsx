"use client";

// Purpose-built replacement for the generic DataBlocks dump on the Gaps page. Leads with a
// scorecard + plain-English "what this means", then each category is a scannable, scored
// DataSection (highlight first, details on click) — and the action-bearing ones link to the
// work orders / content the same gap model already produces.

import Link from "next/link";
import { Card } from "./ui";
import { DataSection } from "./primitives";
import { Term } from "./Term";
import { engineLabel } from "@/lib/engines";

type Json = Record<string, unknown>;
type WeakQuery = { prompt?: string; engine?: string; problem?: string };
type Missing = { topic?: string; asset_type?: string; why?: string };
type Thin = { claim?: string; where_to_get_it?: string };

function arr<T>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : [];
}

export function GapsView({ model, asOf }: { model: Json; asOf?: string }) {
  const summary = (model.summary as string) || "";
  const weak = arr<WeakQuery>(model.weak_queries);
  const missing = arr<Missing>(model.missing_owned_content);
  const thin = arr<Thin>(model.thin_corroboration);
  const schema = arr<string>(model.schema_gaps);
  const priority = arr<string>(model.priority_order);
  const surface = (model.surface_actions as Record<string, unknown>) || {};
  const surfaceEntries = Object.entries(surface).filter(([, v]) => arr<string>(v).length > 0);
  const readiness = model.avg_semantic_readiness as number | undefined;

  return (
    <div className="space-y-4">
      {/* scorecard */}
      <Card>
        <div className="text-sm font-semibold text-gray-900">What the audit found</div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Chip n={weak.length} label="questions AI gets wrong" tone="bad" />
          <Chip n={missing.length} label="pages to create" tone="neutral" />
          <Chip n={thin.length} label="claims needing proof" tone="neutral" />
          <Chip n={schema.length} label="technical (schema) gaps" tone="neutral" />
        </div>
        {summary && (
          <details className="mt-3">
            <summary className="cursor-pointer text-sm font-medium text-gray-500 hover:text-gray-800">
              ▸ Read the full summary
            </summary>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-gray-700">{summary}</p>
          </details>
        )}
        <p className="mt-3 text-xs text-gray-400">
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
              <div className="text-sm font-medium text-gray-800">“{w.prompt}”</div>
              {w.problem && <div className="text-sm text-gray-600">{w.problem}</div>}
              {w.engine && <div className="text-xs text-gray-400">Seen on {engineLabel(w.engine)}</div>}
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
            <li key={i} className="rounded-lg border border-gray-100 p-3">
              <div className="text-sm font-semibold text-gray-800">{m.topic}</div>
              {m.asset_type && <div className="text-xs text-gray-400">{m.asset_type}</div>}
              {m.why && <div className="mt-1 text-sm text-gray-600"><span className="font-medium">What goes in it: </span>{m.why}</div>}
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
          {thin.map((t, i) => (
            <li key={i}>
              <div className="text-sm font-medium text-gray-800">{t.claim}</div>
              {t.where_to_get_it && (
                <div className="text-sm text-gray-600"><span className="font-medium">Get proof from: </span>{t.where_to_get_it}</div>
              )}
            </li>
          ))}
        </ul>
      </DataSection>

      {/* where to show up */}
      {surfaceEntries.length > 0 && (
        <DataSection
          title="Where to show up"
          severity="low"
          headline="Specific, honest actions to add accurate presence on the places AI reads — grouped by platform."
          highlights={[{ label: "Platforms", value: String(surfaceEntries.length) }]}
          detailsLabel="See the actions by platform"
        >
          <div className="space-y-3">
            {surfaceEntries.map(([platform, actions]) => (
              <div key={platform}>
                <div className="text-sm font-semibold capitalize text-gray-800">{platform.replace(/_/g, " ")}</div>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-gray-600">
                  {arr<string>(actions).map((a, i) => <li key={i}>{a}</li>)}
                </ul>
              </div>
            ))}
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
        <p className="mb-2 text-sm text-gray-600">
          <Term name="schema">Schema</Term> is hidden labels in your site&apos;s code that spell out your
          official name, reviews, and FAQs so AI reads them correctly. These {schema.length} are missing —
          a developer task.
        </p>
        <ul className="list-disc space-y-1 pl-5 text-sm text-gray-600">
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
          action={{ label: "Open your work orders", href: "/content/work-orders" }}
          detailsLabel="See the order"
        >
          <ol className="list-decimal space-y-1 pl-5 text-sm text-gray-600">
            {priority.map((p, i) => <li key={i}>{p}</li>)}
          </ol>
        </DataSection>
      )}

      {typeof readiness === "number" && (
        <Card>
          <div className="text-sm">
            <Term name="semantic readiness">Site readiness for AI</Term>:{" "}
            <span className="font-semibold">{Math.round(readiness)}/100</span>{" "}
            <span className="text-gray-500">— how easily AI can pull a clean answer from your pages. Healthy sites score 60+. </span>
            <Link href="/seo" className="font-medium text-blue-600 hover:underline">See your website report →</Link>
          </div>
        </Card>
      )}
    </div>
  );
}

function Chip({ n, label, tone = "neutral" }: { n: number; label: string; tone?: "bad" | "neutral" | "good" }) {
  const c = tone === "bad" && n > 0 ? "bg-rose-50 text-rose-700 border-rose-200" : "bg-gray-100 text-gray-700 border-gray-200";
  return (
    <span className={`rounded-lg border px-2.5 py-1 text-sm ${c}`}>
      <span className="font-semibold">{n}</span> {label}
    </span>
  );
}
