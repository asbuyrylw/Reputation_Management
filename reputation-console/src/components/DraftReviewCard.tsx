"use client";

import { useState } from "react";
import { Card, Badge, Input } from "./ui";
import { StatusBadge } from "@/components/content/StatusBadge";
import { ComplianceNotice } from "@/components/content/ComplianceNotice";
import { DraftImageGallery } from "@/components/content/DraftImageGallery";
import { useApproveDraft, useEditDraft, useRejectDraft, useAtomizeDraft } from "@/lib/hooks";
import type { BadgeTone } from "./ui";
import type { ContentDraft, DraftNeuron } from "@/lib/types";

function quality(s: number | null): { label: string; cls: string } | null {
  if (s == null) return null;
  const v = Math.round(s * 100);
  if (s >= 0.8) return { label: `Strong ${v}/100`, cls: "text-good" };
  if (s >= 0.6) return { label: `OK ${v}/100`, cls: "text-amber" };
  return { label: `Weak ${v}/100`, cls: "text-alert" };
}

// The NeuronWriter SERP content-optimization score. Green when it clears the target (or 80 when
// no target was supplied), amber from 60, rose below — so a glance tells you if the draft covers
// the terms already ranking for its query.
function NeuronGauge({ neuron }: { neuron: DraftNeuron }) {
  const score = Math.round(neuron.content_score);
  const goal = neuron.target != null ? Math.round(neuron.target) : 80;
  const tone: BadgeTone = score >= goal ? "emerald" : score >= 60 ? "amber" : "rose";
  return (
    <span title="NeuronWriter — how well this draft covers the terms already ranking for its query">
      <Badge tone={tone}>
        SERP coverage (NeuronWriter): {score}/100
        {neuron.target != null && <span className="opacity-70"> · target {Math.round(neuron.target)}</span>}
      </Badge>
    </span>
  );
}

// A NeuronWriter-style grade tone from a 0..100 score.
const gTone = (s: number): "good" | "amber" | "alert" => (s >= 80 ? "good" : s >= 60 ? "amber" : "alert");
const G_CHIP: Record<"good" | "amber" | "alert", string> = {
  good: "bg-good-bg text-good",
  amber: "bg-amber-bg text-amber",
  alert: "bg-alert-bg text-alert",
};

// Phase-1 content grades — structure, AEO (per-pillar), readability, NeuronWriter term coverage,
// keyword density, and search-intent shape. A scannable chip strip that expands to the detail +
// the specific fixes, so a reviewer can grade a draft the way NeuronWriter grades a page.
function GradesPanel({ qn }: { qn: NonNullable<ContentDraft["quality_notes"]> }) {
  const { structure, aeo, geo, serp, readability, term_coverage: term, keyword_density: density, intent_serp: intent } = qn;
  if (!structure && !aeo && !geo && !serp && !readability && !term && !intent) return null;
  const geoWeak = (geo?.checks ?? []).filter((c) => !c.ok);
  const chips = [
    geo && typeof geo.score === "number" && { k: "GEO", v: `${geo.score}/100`, tone: gTone(geo.score) },
    !serp?.skipped && typeof serp?.score === "number" && { k: "vs SERP", v: `${serp.score}/100`, tone: gTone(serp.score) },
    structure && { k: "Structure", v: `${structure.score}/100`, tone: gTone(structure.score) },
    aeo && { k: "AEO", v: `${aeo.score}/100`, tone: gTone(aeo.score) },
    readability?.grade != null && { k: "Readability", v: `grade ${readability.grade}`, tone: (readability.grade <= 10 ? "good" : readability.grade <= 12 ? "amber" : "alert") as "good" | "amber" | "alert" },
    term?.covered_pct != null && { k: "SERP terms", v: `${term.covered_pct}%`, tone: gTone(term.covered_pct) },
  ].filter(Boolean) as { k: string; v: string; tone: "good" | "amber" | "alert" }[];
  const fixes = [...(structure?.issues ?? []), ...(aeo?.tips ?? []), ...(readability?.issues ?? []), ...(density?.issues ?? [])];

  return (
    <details className="mt-2 rounded-[12px] border border-line bg-paper/60 p-2.5 text-xs">
      <summary className="flex cursor-pointer flex-wrap items-center gap-1.5">
        <span className="font-mono text-[10px] uppercase tracking-wider text-ink-4">Content grades</span>
        {chips.map((c) => (
          <span key={c.k} className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${G_CHIP[c.tone]}`}>{c.k} {c.v}</span>
        ))}
        {geo?.content_type && <span className="rounded-full bg-line/60 px-2 py-0.5 text-[10px] font-semibold uppercase text-ink-3">{geo.content_type.replace(/_/g, " ")}</span>}
        {intent && <span className="rounded-full bg-indigo-050 px-2 py-0.5 text-[10px] font-semibold uppercase text-indigo-strong">{intent.intent}</span>}
      </summary>
      <div className="mt-2.5 space-y-3">
        {/* GEO — the citability grade (weighted for this content type) + the top fixes */}
        {geo && typeof geo.score === "number" && (
          <div>
            <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-ink-4">
              GEO citability · {geo.score}/100 · {geo.band}{geo.suggested_schema ? ` · schema ${geo.suggested_schema}` : ""}
            </div>
            {geo.note ? (
              <div className="text-ink-3">{geo.note}</div>
            ) : geoWeak.length > 0 ? (
              <div className="space-y-1">
                {geoWeak.slice(0, 5).map((c) => (
                  <div key={c.label} className="flex items-start gap-2">
                    <span className="grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full bg-line-2 text-[9px] text-ink-4">○</span>
                    <span className="flex-1 text-ink-3">{c.fix || c.label}</span>
                    <span className="font-mono text-ink-4">{c.points}/{c.max}</span>
                  </div>
                ))}
              </div>
            ) : <div className="text-good">All citability checks pass ✓</div>}
          </div>
        )}
        {/* SERP benchmark — how the draft stacks up against the pages actually ranking */}
        {serp && !serp.skipped && (
          <div>
            <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-ink-4">
              vs. ranking pages · {serp.covered_pct ?? "—"}% term coverage · {serp.our_words} words{serp.target_words ? ` (target ~${serp.target_words})` : ""}{serp.in_range === false ? " · thin ✗" : ""}
            </div>
            {(serp.terms_missing?.length ?? 0) > 0 && (
              <div className="flex flex-wrap gap-1">
                {serp.terms_missing!.slice(0, 14).map((t) => (
                  <span key={t} className="rounded-full bg-alert-bg px-1.5 py-0.5 text-[10px] text-alert">✗ {t}</span>
                ))}
              </div>
            )}
            {(serp.competitors?.length ?? 0) > 0 && (
              <div className="mt-1.5 text-ink-4">Ranking: {serp.competitors!.slice(0, 3).map((c) => `${(c.title || c.link || "").slice(0, 32)}${c.words ? ` (${c.words}w)` : ""}`).join(" · ")}</div>
            )}
          </div>
        )}
        {/* AEO — will an AI quote this? per-pillar */}
        {aeo && aeo.pillars.length > 0 && (
          <div>
            <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-ink-4">Will AI quote this? · {aeo.score}/100 · schema {aeo.suggested_schema}</div>
            <div className="space-y-1">
              {aeo.pillars.map((p) => (
                <div key={p.name} className="flex items-center gap-2">
                  <span className={`grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full text-[9px] ${p.ok ? "bg-good text-white" : "bg-line-2 text-ink-4"}`}>{p.ok ? "✓" : "○"}</span>
                  <span className={`flex-1 ${p.ok ? "text-ink-2" : "text-ink-3"}`}>{p.name}</span>
                  <span className="font-mono text-ink-4">{p.score}/{p.max}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {/* Structure — heading hierarchy */}
        {structure && structure.structure_map.length > 0 && (
          <div>
            <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-ink-4">Structure · {structure.score}/100 {structure.hierarchy_valid ? "· hierarchy ✓" : "· hierarchy ✗"}</div>
            <div className="space-y-0.5">
              {structure.structure_map.slice(0, 10).map((h, i) => (
                <div key={i} className="truncate text-ink-3" style={{ paddingLeft: `${(h.level - 1) * 12}px` }}>
                  <span className="font-mono text-ink-4">H{h.level}</span> {h.text}
                </div>
              ))}
            </div>
          </div>
        )}
        {/* NeuronWriter term coverage — missing SERP terms to weave in */}
        {term && term.terms_missing.length > 0 && (
          <div>
            <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-ink-4">SERP terms missing ({term.terms_missing.length} of {term.terms_total})</div>
            <div className="flex flex-wrap gap-1">
              {term.terms_missing.slice(0, 16).map((t) => (
                <span key={t} className="rounded-full bg-alert-bg px-1.5 py-0.5 text-[10px] text-alert">✗ {t}</span>
              ))}
            </div>
          </div>
        )}
        {/* Readability numbers */}
        {readability?.grade != null && (
          <div className="text-ink-3">Reading grade <b className="text-ink-2">{readability.grade}</b> · avg sentence {readability.avg_sentence_len} words · {readability.passive_hits} passive{readability.target ? ` · aim ${readability.target}` : ""}</div>
        )}
        {/* Search intent shape */}
        {intent && <div className="text-ink-3">Write it as <b className="text-ink-2">{intent.intent}</b>: {intent.recommended_shape}</div>}
        {/* The fixes to apply */}
        {fixes.length > 0 && (
          <div>
            <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-ink-4">Fixes to raise the grade</div>
            <ul className="space-y-0.5 text-ink-3">
              {fixes.slice(0, 5).map((f, i) => (
                <li key={i}>· {f.label} — <span className="text-ink-4">{f.fix}</span></li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  );
}

// Phase-3 — where the draft sits in the topic-cluster portfolio + concrete internal links to weave
// in (anchor → existing owned/site page, by paragraph). Suggestions only; the reviewer adds them.
function TopicLinksPanel({ qn }: { qn: NonNullable<ContentDraft["quality_notes"]> }) {
  const tc = qn.topic_coverage;
  const links = qn.suggested_links ?? [];
  if (!tc && links.length === 0) return null;
  return (
    <details className="mt-2 rounded-[12px] border border-line bg-paper/60 p-2.5 text-xs">
      <summary className="flex cursor-pointer flex-wrap items-center gap-1.5">
        <span className="font-mono text-[10px] uppercase tracking-wider text-ink-4">Topic &amp; links</span>
        {tc?.score != null && <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${G_CHIP[gTone(tc.score)]}`}>Topic fit {tc.score}/100</span>}
        {tc?.fills_gap && <span className="rounded-full bg-good-bg px-2 py-0.5 text-[10px] font-semibold text-good">Fills a gap</span>}
        {links.length > 0 && <span className="rounded-full bg-indigo-050 px-2 py-0.5 text-[10px] font-semibold text-indigo-strong">{links.length} link{links.length === 1 ? "" : "s"}</span>}
      </summary>
      <div className="mt-2.5 space-y-3">
        {tc && (
          <div>
            <div className="mb-1 text-ink-3">{tc.note}</div>
            {tc.clusters_covered.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {tc.clusters_covered.map((c) => (
                  <span key={c.topic} className={`rounded-full px-1.5 py-0.5 text-[10px] ${c.was_uncovered ? "bg-good-bg text-good" : "bg-line text-ink-3"}`}>{c.was_uncovered ? "★ " : ""}{c.topic}</span>
                ))}
              </div>
            )}
          </div>
        )}
        {links.length > 0 && (
          <div>
            <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-ink-4">Add these internal links</div>
            <ul className="space-y-1">
              {links.map((l, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${l.priority === "high" ? "bg-indigo" : "bg-line-2"}`} />
                  <span className="text-ink-3">
                    ¶{l.paragraph_idx + 1} → <a href={l.target_url} target="_blank" rel="noreferrer" className="font-medium text-indigo hover:underline">{l.anchor_text}</a>
                    <span className="text-ink-4"> — {l.reason}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  );
}

export function DraftReviewCard({
  draft,
  businessId,
  canEdit,
}: {
  draft: ContentDraft;
  businessId: number | null;
  canEdit: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [notes, setNotes] = useState("");
  const [signoff, setSignoff] = useState("");
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(draft.title || "");
  const [editBody, setEditBody] = useState(draft.body || "");
  const approve = useApproveDraft(businessId);
  const reject = useRejectDraft(businessId);
  const edit = useEditDraft(businessId);
  const atomize = useAtomizeDraft(businessId);
  const body = draft.body || "";
  const long = body.length > 400;
  const pending = draft.status === "pending_review" || draft.status === "needs_fix";
  // Long-form pieces (not already a social post) can be atomized into per-platform social drafts.
  const atomizable = long && !(draft.asset_type || "").endsWith("_post");
  const flags = Array.isArray(draft.compliance_flags) ? draft.compliance_flags : [];
  const q = quality(draft.quality_score);
  const added = Array.isArray(draft.highlighted_sections) ? draft.highlighted_sections : [];
  const placeholders = Array.isArray(draft.placeholders_pending) ? draft.placeholders_pending : [];
  // SEO keyword scorecard (from the multi-pass generator's self-check).
  const cov = draft.quality_notes?.keyword_coverage;
  const covCovered = cov?.covered ?? [];
  const covMissing = cov?.missing ?? [];
  const covRate = cov?.rate != null ? Math.round(cov.rate * 100) : null;
  // Extra self-check scorecards: on-page SEO, "will AI quote this?", and a fact-check.
  const onPage = draft.quality_notes?.on_page;
  const citationReady = draft.quality_notes?.citation_ready;
  const factCheck = draft.quality_notes?.fact_check;
  // NeuronWriter SERP content score — only present when content-optimization is configured.
  const neuron = draft.quality_notes?.neuron;
  const scoreTone = (s: number) => (s >= 80 ? "text-good" : s >= 60 ? "text-amber" : "text-alert");
  // "Why this helps" — derived from the question it targets + the work-order instruction.
  const whyHelps = draft.target_query
    ? `Helps your AI reputation + SEO by publishing accurate, ownable content for “${draft.target_query}”.`
    : draft.wo_instruction
      ? `Supports the task: ${draft.wo_instruction.slice(0, 140)}${draft.wo_instruction.length > 140 ? "…" : ""}`
      : null;

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-ink px-1.5 py-0.5 text-xs font-medium text-white">{draft.asset_type}</span>
        <StatusBadge status={draft.status} />
        {q && <span className={`text-xs font-medium ${q.cls}`}>Quality: {q.label}</span>}
        {neuron && <NeuronGauge neuron={neuron} />}
        {draft.compliance_pass === true && (
          <span className="rounded bg-good-bg px-1.5 py-0.5 text-xs text-good">checks passed ✓</span>
        )}
        {draft.compliance_pass === false && (
          <span className="rounded bg-alert-bg px-1.5 py-0.5 text-xs text-alert">flagged — review ✗</span>
        )}
        {draft.compliance_pass == null && (
          <span className="rounded bg-amber-bg px-1.5 py-0.5 text-xs text-amber">not checked yet</span>
        )}
      </div>
      {editing ? (
        <div className="mt-2 space-y-2">
          <Input
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            placeholder="Title"
            className="font-medium"
          />
          <textarea
            value={editBody}
            onChange={(e) => setEditBody(e.target.value)}
            rows={12}
            className="w-full rounded-md border border-line-2 px-3 py-2 font-mono text-sm text-ink-2"
          />
          <div className="flex items-center gap-2">
            <button
              disabled={edit.isPending || !editTitle.trim() || !editBody.trim()}
              onClick={() =>
                edit.mutate(
                  { draftId: draft.id, title: editTitle, body: editBody },
                  { onSuccess: () => setEditing(false) },
                )
              }
              className="rounded-md bg-ink px-3 py-1.5 text-sm font-medium text-white hover:bg-ink-2 disabled:opacity-50"
            >
              {edit.isPending ? "Saving…" : "Save changes"}
            </button>
            <button
              onClick={() => { setEditing(false); setEditTitle(draft.title || ""); setEditBody(draft.body || ""); }}
              className="rounded-md border border-line-2 px-3 py-1.5 text-sm text-ink-2 hover:bg-line/60"
            >
              Cancel
            </button>
            <span className="text-xs text-ink-4">Edit the copy, then approve the revised version.</span>
          </div>
        </div>
      ) : (
        <>
          <div className="mt-2 text-sm font-medium text-ink">{draft.title}</div>
          {draft.target_query && (
            <div className="text-xs text-ink-3">Answers the question: “{draft.target_query}”</div>
          )}
          <p className="mt-1 whitespace-pre-wrap text-sm text-ink-2">
            {open || !long ? body : body.slice(0, 400) + "…"}
          </p>
          {long && (
            <button onClick={() => setOpen((o) => !o)} className="mt-1 text-xs text-indigo hover:underline">
              {open ? "Show less" : "Show full draft"}
            </button>
          )}
        </>
      )}
      {flags.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-xs text-alert">
          {flags.map((f, i) => (
            <li key={i}>{String(f)}</li>
          ))}
        </ul>
      )}

      {/* compliance language the AI auto-added — the human confirms it's accurate */}
      {added.length > 0 && (
        <ComplianceNotice tone="info" className="mt-2" title="We added compliance language — please confirm it's accurate:">
          <ul className="list-disc pl-5">
            {added.map((a, i) => <li key={i}>{a?.note || a?.type || "compliance edit"}</li>)}
          </ul>
        </ComplianceNotice>
      )}

      {/* unresolved [INSERT: ...] placeholders — a red pre-publish checklist that blocks approval */}
      {placeholders.length > 0 && (
        <ComplianceNotice tone="bad" className="mt-2" title={`Fill these in before publishing (${placeholders.length}):`}>
          <ul className="space-y-0.5">
            {placeholders.map((p, i) => (
              <li key={i} className="font-mono">☐ {p}</li>
            ))}
          </ul>
          <div className="mt-1 text-ink-3">Click “Edit” and replace each one, then approve.</div>
        </ComplianceNotice>
      )}

      {/* SEO keyword scorecard — does this draft contain the language it needs to rank? */}
      {(covCovered.length > 0 || covMissing.length > 0) && (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer text-slate-500 hover:text-slate-700">
            Keyword coverage{covRate != null ? `: ${covRate}%` : ""} ({covCovered.length} included{covMissing.length ? `, ${covMissing.length} missing` : ""})
          </summary>
          <div className="mt-1 space-y-1.5 rounded bg-paper p-2">
            {covCovered.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {covCovered.slice(0, 14).map((k) => (
                  <span key={k} className="rounded-full bg-good-bg px-1.5 py-0.5 text-[10px] text-good">✓ {k}</span>
                ))}
              </div>
            )}
            {covMissing.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {covMissing.slice(0, 12).map((k) => (
                  <span key={k} className="rounded-full bg-alert-bg px-1.5 py-0.5 text-[10px] text-alert">✗ {k}</span>
                ))}
              </div>
            )}
            <p className="text-[10px] text-ink-4">Target keywords this draft includes vs. is missing — edit to weave in the important ones.</p>
          </div>
        </details>
      )}

      {/* Draft-quality scorecards: on-page SEO, AI-citability, and a best-effort fact-check */}
      {(onPage || citationReady || factCheck) && (
        <div className="mt-2 space-y-1.5 rounded-md border border-line bg-paper/60 p-2 text-xs">
          {onPage && (
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-medium text-ink-3">On-page SEO</span>
                <span className={`font-semibold ${scoreTone(onPage.score)}`}>{onPage.score}/100</span>
                <span className="text-ink-4">· {onPage.word_count} words · {onPage.images_with_alt}/{onPage.images} images with alt</span>
              </div>
              {onPage.issues.length > 0 && (
                <ul className="mt-0.5 space-y-0.5 text-ink-3">
                  {onPage.issues.slice(0, 2).map((it, i) => (
                    <li key={i}>· {it.label} — <span className="text-ink-4">{it.fix}</span></li>
                  ))}
                </ul>
              )}
              {onPage.suggested_schema && (
                <div className="mt-0.5 text-[10px] text-ink-4">Suggested schema: {onPage.suggested_schema}</div>
              )}
            </div>
          )}
          {citationReady && (
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-medium text-ink-3">Will AI quote this?</span>
                <span className={`font-semibold ${scoreTone(citationReady.score)}`}>{citationReady.score}/100</span>
                <span className="text-ink-4">· {citationReady.faq_headings} Q&amp;A heading{citationReady.faq_headings === 1 ? "" : "s"}</span>
              </div>
              {citationReady.tips.length > 0 && (
                <ul className="mt-0.5 space-y-0.5 text-ink-3">
                  {citationReady.tips.slice(0, 2).map((t, i) => (
                    <li key={i}>· {t.label} — <span className="text-ink-4">{t.fix}</span></li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {factCheck && factCheck.unverified > 0 && (
            <ComplianceNotice tone="info" title={`${factCheck.unverified} claim${factCheck.unverified === 1 ? "" : "s"} need confirming`}>
              <ul className="space-y-0.5">
                {factCheck.claims
                  .filter((c) => c.status !== "verified")
                  .slice(0, 3)
                  .map((c, i) => (
                    <li key={i}>· “{c.claim}”{c.note ? ` — ${c.note}` : ""}</li>
                  ))}
              </ul>
              <div className="mt-0.5 text-[10px] text-ink-4">May still be true — confirm before publishing.</div>
            </ComplianceNotice>
          )}
        </div>
      )}

      {/* Phase-1 NeuronWriter-style content grades — structure, AEO, readability, term coverage, intent */}
      {draft.quality_notes && <GradesPanel qn={draft.quality_notes} />}

      {/* Phase-3 — topic-portfolio coverage + concrete in-draft internal-link suggestions */}
      {draft.quality_notes && <TopicLinksPanel qn={draft.quality_notes} />}

      {/* Phase-4 — generated images for this draft (from its IMAGE markers), with approve/reject */}
      <DraftImageGallery businessId={businessId} draftId={draft.id} markers={draft.quality_notes?.image_markers ?? []} canEdit={canEdit} />

      {whyHelps && <p className="mt-2 text-xs text-ink-3">💡 {whyHelps}</p>}
      {/* Phase 1 — the specific gap this piece traces back to, so a reviewer sees WHAT it fixes. */}
      {(draft.gap_specifics?.source_query || draft.gap_source || draft.why_helps_ai_rep || draft.why_helps_seo) && (
        <div className="mt-2 rounded-[10px] border border-line bg-paper/60 px-2.5 py-1.5 text-[11px] text-ink-3">
          <span className="font-mono text-[10px] uppercase tracking-wider text-ink-4">Closes gap</span>
          {draft.gap_specifics?.source_query && <> · fixes the answer to <b className="text-ink-2">“{draft.gap_specifics.source_query}”</b></>}
          {draft.gap_source && <> · from <span className="text-ink-2">{draft.gap_source}</span></>}
          <div className="mt-0.5 flex flex-wrap gap-x-3">
            {draft.why_helps_ai_rep && <span>🤖 {draft.why_helps_ai_rep}</span>}
            {draft.why_helps_seo && <span>🔍 {draft.why_helps_seo}</span>}
          </div>
        </div>
      )}

      {/* Phase-5 atomization — turn this long-form piece into per-platform social posts (human-gated) */}
      {canEdit && atomizable && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={atomize.isPending}
            onClick={() => atomize.mutate({ draftId: draft.id })}
            className="inline-flex items-center gap-1.5 rounded-md border border-line-2 px-2.5 py-1 text-xs font-semibold text-ink-2 hover:bg-line/60 disabled:opacity-50"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-3.5 w-3.5 text-indigo"><path d="M4 11a9 9 0 0 1 9 9M4 4a16 16 0 0 1 16 16" /><circle cx="5" cy="19" r="1" /></svg>
            {atomize.isPending ? "Creating…" : "Create social posts"}
          </button>
          {atomize.isSuccess && (
            <span className="text-xs text-good">Created {(atomize.data as { created?: number } | undefined)?.created ?? 0} social draft(s) — review them in Drafts.</span>
          )}
          {atomize.isError && <span className="text-xs text-alert">Couldn&apos;t create posts — try again.</span>}
        </div>
      )}

      {/* unscreened draft (compliance not confirmed) needs a principal sign-off reason to approve */}
      {canEdit && pending && draft.compliance_pass == null && !editing && (
        <ComplianceNotice tone="info" className="mt-3">
          <label className="font-medium text-amber">
            Compliance wasn&apos;t auto-confirmed — add a principal sign-off reason to approve:
            <input value={signoff} onChange={(e) => setSignoff(e.target.value)} placeholder="e.g. Reviewed by principal; disclosures verified"
              className="mt-1 w-full rounded border border-amber/40 bg-card px-2 py-1 text-sm text-ink-2" />
          </label>
        </ComplianceNotice>
      )}

      {canEdit && pending && !rejecting && !editing && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            disabled={approve.isPending || placeholders.length > 0 || (draft.compliance_pass == null && !signoff.trim())}
            title={placeholders.length > 0 ? "Fill in the placeholders first" : draft.compliance_pass == null && !signoff.trim() ? "Add a sign-off reason first" : undefined}
            onClick={() => approve.mutate({ draftId: draft.id, override_reason: draft.compliance_pass == null ? signoff.trim() : undefined })}
            className="rounded-md bg-good px-3 py-1.5 text-sm font-medium text-white hover:brightness-95 disabled:opacity-50"
          >
            Approve &amp; publish
          </button>
          <button
            onClick={() => { setEditTitle(draft.title || ""); setEditBody(draft.body || ""); setEditing(true); }}
            className="rounded-md border border-line-2 px-3 py-1.5 text-sm text-ink-2 hover:bg-line/60"
          >
            Edit
          </button>
          <button
            disabled={reject.isPending}
            onClick={() => setRejecting(true)}
            className="rounded-md border border-line-2 px-3 py-1.5 text-sm text-ink-2 hover:bg-line/60"
          >
            Send back
          </button>
          <span className="text-xs text-ink-4">Approving adds it to your published content.</span>
        </div>
      )}
      {canEdit && pending && rejecting && !editing && (
        <div className="mt-3">
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="What should change? (optional)"
            rows={2}
            className="w-full rounded-md border border-line-2 px-3 py-2 text-sm text-ink-2"
          />
          <div className="mt-2 flex gap-2">
            <button
              disabled={reject.isPending}
              onClick={() => reject.mutate({ draftId: draft.id, notes: notes || undefined }, { onSuccess: () => setRejecting(false) })}
              className="rounded-md bg-ink px-3 py-1.5 text-sm font-medium text-white hover:bg-ink-2 disabled:opacity-50"
            >
              Send back for changes
            </button>
            <button onClick={() => { setRejecting(false); setNotes(""); }} className="rounded-md border border-line-2 px-3 py-1.5 text-sm text-ink-2 hover:bg-line/60">
              Cancel
            </button>
          </div>
        </div>
      )}
      {(approve.isError || reject.isError || edit.isError) && (
        <p className="mt-2 text-xs text-alert">Action failed — please retry.</p>
      )}
    </Card>
  );
}
