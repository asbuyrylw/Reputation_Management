"use client";

import { useState } from "react";
import { Card, Badge } from "./ui";
import { useApproveDraft, useEditDraft, useRejectDraft } from "@/lib/hooks";
import type { BadgeTone } from "./ui";
import type { ContentDraft, DraftNeuron } from "@/lib/types";

const STATUS_WORDS: Record<string, string> = {
  pending_review: "Waiting for you",
  needs_fix: "Needs a fix",
  approved: "Approved",
  rejected: "Rejected",
};
const STATUS_COLORS: Record<string, string> = {
  pending_review: "bg-amber-100 text-amber-800",
  needs_fix: "bg-orange-100 text-orange-800",
  approved: "bg-emerald-100 text-emerald-800",
  rejected: "bg-slate-200 text-slate-600",
};

function quality(s: number | null): { label: string; cls: string } | null {
  if (s == null) return null;
  const v = Math.round(s * 100);
  if (s >= 0.8) return { label: `Strong ${v}/100`, cls: "text-emerald-700" };
  if (s >= 0.6) return { label: `OK ${v}/100`, cls: "text-amber-700" };
  return { label: `Weak ${v}/100`, cls: "text-rose-600" };
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
  const { structure, aeo, readability, term_coverage: term, keyword_density: density, intent_serp: intent } = qn;
  if (!structure && !aeo && !readability && !term && !intent) return null;
  const chips = [
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
        {intent && <span className="rounded-full bg-indigo-050 px-2 py-0.5 text-[10px] font-semibold uppercase text-indigo-strong">{intent.intent}</span>}
      </summary>
      <div className="mt-2.5 space-y-3">
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
  const body = draft.body || "";
  const long = body.length > 400;
  const pending = draft.status === "pending_review" || draft.status === "needs_fix";
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
  const scoreTone = (s: number) => (s >= 80 ? "text-emerald-700" : s >= 60 ? "text-amber-700" : "text-rose-600");
  // "Why this helps" — derived from the question it targets + the work-order instruction.
  const whyHelps = draft.target_query
    ? `Helps your AI reputation + SEO by publishing accurate, ownable content for “${draft.target_query}”.`
    : draft.wo_instruction
      ? `Supports the task: ${draft.wo_instruction.slice(0, 140)}${draft.wo_instruction.length > 140 ? "…" : ""}`
      : null;

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-slate-900 px-1.5 py-0.5 text-xs font-medium text-white">{draft.asset_type}</span>
        <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_COLORS[draft.status] || "bg-slate-100 text-slate-700"}`}>
          {STATUS_WORDS[draft.status] ?? draft.status.replace(/_/g, " ")}
        </span>
        {q && <span className={`text-xs font-medium ${q.cls}`}>Quality: {q.label}</span>}
        {neuron && <NeuronGauge neuron={neuron} />}
        {draft.compliance_pass === true && (
          <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-xs text-emerald-700">checks passed ✓</span>
        )}
        {draft.compliance_pass === false && (
          <span className="rounded bg-rose-50 px-1.5 py-0.5 text-xs text-rose-700">flagged — review ✗</span>
        )}
        {draft.compliance_pass == null && (
          <span className="rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-700">not checked yet</span>
        )}
      </div>
      {editing ? (
        <div className="mt-2 space-y-2">
          <input
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            placeholder="Title"
            className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium"
          />
          <textarea
            value={editBody}
            onChange={(e) => setEditBody(e.target.value)}
            rows={12}
            className="w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm"
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
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {edit.isPending ? "Saving…" : "Save changes"}
            </button>
            <button
              onClick={() => { setEditing(false); setEditTitle(draft.title || ""); setEditBody(draft.body || ""); }}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
            >
              Cancel
            </button>
            <span className="text-xs text-slate-400">Edit the copy, then approve the revised version.</span>
          </div>
        </div>
      ) : (
        <>
          <div className="mt-2 text-sm font-medium text-slate-900">{draft.title}</div>
          {draft.target_query && (
            <div className="text-xs text-slate-500">Answers the question: “{draft.target_query}”</div>
          )}
          <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">
            {open || !long ? body : body.slice(0, 400) + "…"}
          </p>
          {long && (
            <button onClick={() => setOpen((o) => !o)} className="mt-1 text-xs text-indigo-600 hover:underline">
              {open ? "Show less" : "Show full draft"}
            </button>
          )}
        </>
      )}
      {flags.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-xs text-rose-700">
          {flags.map((f, i) => (
            <li key={i}>{String(f)}</li>
          ))}
        </ul>
      )}

      {/* compliance language the AI auto-added — the human confirms it's accurate */}
      {added.length > 0 && (
        <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
          <div className="font-semibold">We added compliance language — please confirm it&apos;s accurate:</div>
          <ul className="mt-1 list-disc pl-5">
            {added.map((a, i) => <li key={i}>{a?.note || a?.type || "compliance edit"}</li>)}
          </ul>
        </div>
      )}

      {/* unresolved [INSERT: ...] placeholders — a red pre-publish checklist that blocks approval */}
      {placeholders.length > 0 && (
        <div className="mt-2 rounded-md border border-rose-200 bg-rose-50 p-2 text-xs text-rose-700">
          <div className="font-semibold">Fill these in before publishing ({placeholders.length}):</div>
          <ul className="mt-1 space-y-0.5">
            {placeholders.map((p, i) => (
              <li key={i} className="font-mono">☐ {p}</li>
            ))}
          </ul>
          <div className="mt-1 text-rose-500">Click “Edit” and replace each one, then approve.</div>
        </div>
      )}

      {/* SEO keyword scorecard — does this draft contain the language it needs to rank? */}
      {(covCovered.length > 0 || covMissing.length > 0) && (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer text-slate-500 hover:text-slate-700">
            Keyword coverage{covRate != null ? `: ${covRate}%` : ""} ({covCovered.length} included{covMissing.length ? `, ${covMissing.length} missing` : ""})
          </summary>
          <div className="mt-1 space-y-1.5 rounded bg-slate-50 p-2">
            {covCovered.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {covCovered.slice(0, 14).map((k) => (
                  <span key={k} className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] text-emerald-700">✓ {k}</span>
                ))}
              </div>
            )}
            {covMissing.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {covMissing.slice(0, 12).map((k) => (
                  <span key={k} className="rounded-full bg-rose-50 px-1.5 py-0.5 text-[10px] text-rose-600">✗ {k}</span>
                ))}
              </div>
            )}
            <p className="text-[10px] text-slate-400">Target keywords this draft includes vs. is missing — edit to weave in the important ones.</p>
          </div>
        </details>
      )}

      {/* Draft-quality scorecards: on-page SEO, AI-citability, and a best-effort fact-check */}
      {(onPage || citationReady || factCheck) && (
        <div className="mt-2 space-y-1.5 rounded-md border border-slate-100 bg-slate-50/60 p-2 text-xs">
          {onPage && (
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-medium text-slate-600">On-page SEO</span>
                <span className={`font-semibold ${scoreTone(onPage.score)}`}>{onPage.score}/100</span>
                <span className="text-slate-400">· {onPage.word_count} words · {onPage.images_with_alt}/{onPage.images} images with alt</span>
              </div>
              {onPage.issues.length > 0 && (
                <ul className="mt-0.5 space-y-0.5 text-slate-500">
                  {onPage.issues.slice(0, 2).map((it, i) => (
                    <li key={i}>· {it.label} — <span className="text-slate-400">{it.fix}</span></li>
                  ))}
                </ul>
              )}
              {onPage.suggested_schema && (
                <div className="mt-0.5 text-[10px] text-slate-400">Suggested schema: {onPage.suggested_schema}</div>
              )}
            </div>
          )}
          {citationReady && (
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-medium text-slate-600">Will AI quote this?</span>
                <span className={`font-semibold ${scoreTone(citationReady.score)}`}>{citationReady.score}/100</span>
                <span className="text-slate-400">· {citationReady.faq_headings} Q&amp;A heading{citationReady.faq_headings === 1 ? "" : "s"}</span>
              </div>
              {citationReady.tips.length > 0 && (
                <ul className="mt-0.5 space-y-0.5 text-slate-500">
                  {citationReady.tips.slice(0, 2).map((t, i) => (
                    <li key={i}>· {t.label} — <span className="text-slate-400">{t.fix}</span></li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {factCheck && factCheck.unverified > 0 && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-1.5 text-amber-800">
              <div className="font-medium">
                {factCheck.unverified} claim{factCheck.unverified === 1 ? "" : "s"} need confirming
              </div>
              <ul className="mt-0.5 space-y-0.5 text-amber-700">
                {factCheck.claims
                  .filter((c) => c.status !== "verified")
                  .slice(0, 3)
                  .map((c, i) => (
                    <li key={i}>· “{c.claim}”{c.note ? ` — ${c.note}` : ""}</li>
                  ))}
              </ul>
              <div className="mt-0.5 text-[10px] text-amber-600">May still be true — confirm before publishing.</div>
            </div>
          )}
        </div>
      )}

      {/* Phase-1 NeuronWriter-style content grades — structure, AEO, readability, term coverage, intent */}
      {draft.quality_notes && <GradesPanel qn={draft.quality_notes} />}

      {whyHelps && <p className="mt-2 text-xs text-slate-500">💡 {whyHelps}</p>}

      {/* unscreened draft (compliance not confirmed) needs a principal sign-off reason to approve */}
      {canEdit && pending && draft.compliance_pass == null && !editing && (
        <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-2">
          <label className="text-xs font-medium text-amber-800">
            Compliance wasn&apos;t auto-confirmed — add a principal sign-off reason to approve:
            <input value={signoff} onChange={(e) => setSignoff(e.target.value)} placeholder="e.g. Reviewed by principal; disclosures verified"
              className="mt-1 w-full rounded border border-amber-300 px-2 py-1 text-sm" />
          </label>
        </div>
      )}

      {canEdit && pending && !rejecting && !editing && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            disabled={approve.isPending || placeholders.length > 0 || (draft.compliance_pass == null && !signoff.trim())}
            title={placeholders.length > 0 ? "Fill in the placeholders first" : draft.compliance_pass == null && !signoff.trim() ? "Add a sign-off reason first" : undefined}
            onClick={() => approve.mutate({ draftId: draft.id, override_reason: draft.compliance_pass == null ? signoff.trim() : undefined })}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Approve &amp; publish
          </button>
          <button
            onClick={() => { setEditTitle(draft.title || ""); setEditBody(draft.body || ""); setEditing(true); }}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
          >
            Edit
          </button>
          <button
            disabled={reject.isPending}
            onClick={() => setRejecting(true)}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
          >
            Send back
          </button>
          <span className="text-xs text-slate-400">Approving adds it to your published content.</span>
        </div>
      )}
      {canEdit && pending && rejecting && !editing && (
        <div className="mt-3">
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="What should change? (optional)"
            rows={2}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <div className="mt-2 flex gap-2">
            <button
              disabled={reject.isPending}
              onClick={() => reject.mutate({ draftId: draft.id, notes: notes || undefined }, { onSuccess: () => setRejecting(false) })}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              Send back for changes
            </button>
            <button onClick={() => { setRejecting(false); setNotes(""); }} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100">
              Cancel
            </button>
          </div>
        </div>
      )}
      {(approve.isError || reject.isError || edit.isError) && (
        <p className="mt-2 text-xs text-rose-600">Action failed — please retry.</p>
      )}
    </Card>
  );
}
