"use client";

import { useState } from "react";
import { Card } from "./ui";
import { SentimentBadge } from "./SentimentBadge";
import { RepScoreBadge } from "./RepScoreBadge";
import type { Answer } from "@/lib/types";

export function AnswerCard({ a }: { a: Answer }) {
  const [open, setOpen] = useState(false);
  const text = a.answer_text || "";
  const sources = Array.isArray(a.cited_sources) ? a.cited_sources : [];
  const long = text.length > 280;

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-slate-900 px-1.5 py-0.5 text-xs font-medium text-white">{a.engine}</span>
        <SentimentBadge sentiment={a.sentiment} />
        {a.goal_alignment != null && <RepScoreBadge goalAlignment={a.goal_alignment} />}
        {a.entity_confusion === true ? (
          <span
            className="rounded bg-purple-50 px-1.5 py-0.5 text-xs text-purple-700"
            title="The engine described a DIFFERENT same-named entity, not this business — a disambiguation/grounding failure."
          >
            wrong entity
          </span>
        ) : (
          a.awareness === false && (
            <span
              className="rounded bg-indigo-50 px-1.5 py-0.5 text-xs text-indigo-700"
              title="The engine did not recognize this business — an awareness gap (a void to fill)."
            >
              no awareness
            </span>
          )
        )}
        {a.mentions_contested && (
          <span className="rounded bg-rose-50 px-1.5 py-0.5 text-xs text-rose-700">contested</span>
        )}
        {a.surfaces_owned && (
          <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-xs text-emerald-700">owned source</span>
        )}
        {a.persona && (
          <span className="text-xs text-slate-400">
            {a.persona}
            {a.location ? ` · ${a.location}` : ""}
          </span>
        )}
      </div>
      <div className="mt-2 text-sm font-medium text-slate-900">{a.prompt}</div>
      <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">
        {open || !long ? text : text.slice(0, 280) + "…"}
      </p>
      {long && (
        <button onClick={() => setOpen((o) => !o)} className="mt-1 text-xs text-indigo-600 hover:underline">
          {open ? "Show less" : "Show more"}
        </button>
      )}
      {sources.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {sources.map((s, i) => (
            <span key={i} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
              {typeof s === "string" ? s : JSON.stringify(s)}
            </span>
          ))}
        </div>
      )}
    </Card>
  );
}
