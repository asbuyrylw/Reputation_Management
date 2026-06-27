"use client";

// AI-crawler readiness — two SEO-for-AI checks in one card:
//  1. schema.org coverage: which structured-data types are deployed vs. recommended-missing
//     (chips), plus a one-line verdict.
//  2. llms.txt: the generated content shown in a <pre>, with copy-to-clipboard and a
//     download-as-llms.txt button (so it can be dropped at the site root).

import { useState } from "react";
import { useLlmsTxt, useSchemaVerify } from "@/lib/hooks";
import { downloadText } from "@/lib/download";
import { Card } from "./ui";

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <button
      type="button"
      onClick={copy}
      className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
    >
      {copied ? "Copied ✓" : label}
    </button>
  );
}

export function AiCrawlerReadinessCard({ businessId }: { businessId: number | null }) {
  const { data: schema } = useSchemaVerify(businessId);
  const { data: llms } = useLlmsTxt(businessId);

  if (!schema && !llms) return null;

  const verdictTone =
    schema && schema.recommended_missing.length === 0
      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
      : "bg-amber-50 text-amber-700 ring-amber-200";

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">AI-crawler readiness</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            How easily AI assistants can read and cite your site — structured data (schema.org) and a generated{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5 text-[11px]">llms.txt</code> map for AI crawlers.
          </p>
        </div>
      </div>

      {/* schema.org coverage */}
      {schema && (
        <div className="mt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Structured data ({schema.checked_pages} page{schema.checked_pages === 1 ? "" : "s"} checked)
            </div>
            {schema.verdict && (
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${verdictTone}`}>
                {schema.verdict}
              </span>
            )}
          </div>
          <div className="mt-2">
            <div className="text-xs text-slate-500">Deployed</div>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {schema.deployed_schema.length > 0 ? (
                schema.deployed_schema.map((t) => (
                  <span
                    key={t}
                    className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200"
                  >
                    {t}
                  </span>
                ))
              ) : (
                <span className="text-xs text-slate-400">None detected yet.</span>
              )}
            </div>
          </div>
          {schema.recommended_missing.length > 0 && (
            <div className="mt-2">
              <div className="text-xs text-slate-500">Recommended (missing)</div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {schema.recommended_missing.map((t) => (
                  <span
                    key={t}
                    className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 ring-1 ring-inset ring-amber-200"
                  >
                    + {t}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* llms.txt block */}
      {llms && (
        <div className="mt-4 border-t border-slate-100 pt-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              llms.txt{llms.page_count ? ` · ${llms.page_count} page${llms.page_count === 1 ? "" : "s"}` : ""}
            </div>
            <div className="flex items-center gap-2">
              <CopyButton text={llms.content} label="Copy" />
              <button
                type="button"
                onClick={() => downloadText(llms.content, "llms.txt")}
                className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
              >
                Download llms.txt
              </button>
            </div>
          </div>
          {llms.note && <p className="mt-1.5 text-xs text-slate-500">{llms.note}</p>}
          <pre className="mt-2 max-h-72 overflow-auto rounded-lg bg-slate-50 p-3 text-[11px] leading-relaxed text-slate-700 ring-1 ring-inset ring-slate-200">
            {llms.content}
          </pre>
        </div>
      )}
    </Card>
  );
}
