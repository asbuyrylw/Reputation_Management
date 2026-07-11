"use client";

// Source material + brand rules — what the content generators (Claude + NotebookLM) are grounded in.
// The brand guardrails lead EVERY generation prompt (e.g. "always Team Unstoppable, never Primerica");
// uploaded documents become the client's knowledge corpus so content is built on their real facts.

import { useRef, useState } from "react";
import { useBusiness } from "@/lib/business";
import { useBrandGuardrails, useSetBrandGuardrails, useSourceDocuments, useAddSourceDoc, useUploadSourceDoc, useDeleteSourceDoc } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import type { SourceDocument } from "@/lib/types";

export default function SourceMaterialPage() {
  const { businessId, businesses, loading, canEdit } = useBusiness();
  const guard = useBrandGuardrails(businessId);
  const setGuard = useSetBrandGuardrails(businessId);
  const docs = useSourceDocuments(businessId);
  const addDoc = useAddSourceDoc(businessId);
  const upload = useUploadSourceDoc(businessId);
  const del = useDeleteSourceDoc(businessId);
  const fileRef = useRef<HTMLInputElement>(null);
  const [guardText, setGuardText] = useState<string | null>(null);
  const [noteTitle, setNoteTitle] = useState("");
  const [noteBody, setNoteBody] = useState("");
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);

  if (loading) return <Spinner />;
  if (businesses.length === 0) return <div><PageHeader eyebrow="Content · Source material" title="Source material" /><Card><p className="py-4 text-ink-3">Set up a business first.</p></Card></div>;

  const g = guardText ?? guard.data?.brand_guardrails ?? "";
  const documents = docs.data?.documents ?? [];

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;
    // Bulk upload: process each file in turn, reporting running progress. One failure doesn't
    // abort the rest — the doc that failed is named so the owner can retry just that one.
    const ok: string[] = [];
    const failed: string[] = [];
    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      setUploadMsg(files.length > 1 ? `Uploading ${i + 1} of ${files.length}: ${f.name}…` : "Uploading…");
      try {
        const r = await upload.mutateAsync(f);
        ok.push(r.title || f.name);
      } catch {
        failed.push(f.name);
      }
    }
    const parts: string[] = [];
    if (ok.length) parts.push(`Added ${ok.length} document${ok.length > 1 ? "s" : ""}`);
    if (failed.length) parts.push(`${failed.length} failed (${failed.join(", ")})`);
    setUploadMsg(parts.join(" · ") || "Nothing uploaded");
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <div>
      <PageHeader eyebrow="Content · Source material" title="Brand rules & source material"
        subtitle="This is what every generator — blog, article, video, podcast, infographic — is grounded in. The brand rules lead every prompt; the documents give it your real facts." />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* Brand guardrails */}
        <Card className="flex flex-col">
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Brand rules</h3>
          <p className="mt-0.5 mb-3 text-xs text-slate-500">Absolute rules injected at the top of every generation — brand name, what to never say, tone, compliance. (e.g. always brand as your team, never the parent company.)</p>
          <textarea value={g} onChange={(e) => setGuardText(e.target.value)} disabled={!canEdit} rows={9}
            className="flex-1 rounded-[10px] border border-line bg-paper p-3 font-mono text-[12.5px] leading-relaxed text-ink outline-none focus:border-indigo"
            placeholder="e.g. Always brand this content as Team Unstoppable — never present it as Primerica…" />
          {canEdit && (
            <div className="mt-3 flex items-center gap-2">
              <button onClick={() => setGuard.mutate(g)} disabled={setGuard.isPending}
                className="rounded-[10px] bg-indigo px-4 py-2 text-[13px] font-semibold text-white hover:bg-indigo-strong disabled:opacity-60">
                {setGuard.isPending ? "Saving…" : "Save brand rules"}</button>
              {setGuard.isSuccess && <span className="text-[12px] text-good">✓ Saved</span>}
            </div>
          )}
        </Card>

        {/* Upload + add */}
        <Card className="flex flex-col">
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Add source material</h3>
          <p className="mt-0.5 mb-3 text-xs text-slate-500">Upload brand docs, scripts, product one-pagers, testimonials, FAQs — anything the AI should build content from. Select several at once. TXT / MD / PDF / DOCX.</p>
          {canEdit && (
            <>
              <input ref={fileRef} type="file" multiple accept=".txt,.md,.csv,.pdf,.docx" onChange={onFile} className="hidden" />
              <button onClick={() => fileRef.current?.click()} disabled={upload.isPending}
                className="rounded-[10px] border-2 border-dashed border-line-2 bg-paper px-4 py-6 text-[14px] font-semibold text-ink-2 hover:border-indigo hover:text-indigo disabled:opacity-60">
                {upload.isPending ? "Uploading…" : "⬆  Upload documents"}</button>
              {uploadMsg && <div className="mt-2 text-[12px] text-ink-3">{uploadMsg}</div>}

              <div className="mt-4 border-t border-line pt-4">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Or paste text</div>
                <input value={noteTitle} onChange={(e) => setNoteTitle(e.target.value)} placeholder="Title (e.g. About Team Unstoppable)"
                  className="mb-2 w-full rounded-[8px] border border-line bg-paper px-3 py-1.5 text-[13px] outline-none focus:border-indigo" />
                <textarea value={noteBody} onChange={(e) => setNoteBody(e.target.value)} rows={4} placeholder="Paste facts, bios, key messaging…"
                  className="w-full rounded-[8px] border border-line bg-paper p-2.5 text-[13px] outline-none focus:border-indigo" />
                <button onClick={() => { if (noteBody.trim()) addDoc.mutate({ title: noteTitle || "Note", content: noteBody }, { onSuccess: () => { setNoteTitle(""); setNoteBody(""); } }); }}
                  disabled={addDoc.isPending || !noteBody.trim()}
                  className="mt-2 rounded-[10px] border border-line bg-white px-3.5 py-1.5 text-[13px] font-semibold text-ink hover:bg-paper disabled:opacity-50">
                  {addDoc.isPending ? "Adding…" : "Add note"}</button>
              </div>
            </>
          )}
        </Card>
      </div>

      {/* Corpus list */}
      <Card className="mt-5">
        <h3 className="mb-1 text-base font-semibold tracking-tight text-slate-900">Your knowledge corpus <span className="font-mono text-[12px] font-normal text-ink-4">({documents.length})</span></h3>
        <p className="mb-3 text-xs text-slate-500">Everything here grounds content generation. Delete anything out of date.</p>
        {docs.isLoading ? <Spinner /> : documents.length === 0 ? (
          <p className="py-4 text-center text-[13.5px] text-ink-4">No source material yet. Upload documents or paste text so the AI writes from your real facts, not generic web content.</p>
        ) : (
          <ul className="divide-y divide-line">
            {documents.map((d: SourceDocument) => (
              <li key={d.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <div className="truncate text-[14px] font-medium text-ink">{d.title || "Untitled"}</div>
                  <div className="font-mono text-[11px] text-ink-4">{d.source_type} · ~{(d.tokens ?? 0).toLocaleString()} tokens{d.created_at ? ` · ${new Date(d.created_at).toLocaleDateString()}` : ""}</div>
                </div>
                {canEdit && <button onClick={() => del.mutate(d.id)} className="shrink-0 rounded-lg px-2.5 py-1 text-[12px] font-semibold text-rose-600 hover:bg-rose-50">Delete</button>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
