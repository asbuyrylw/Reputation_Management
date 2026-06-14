"use client";

import { useState } from "react";
import { Card } from "./ui";
import { SentimentBadge } from "./SentimentBadge";
import type { Answer } from "@/lib/types";

export function AnswerCard({ a }: { a: Answer }) {
  const [open, setOpen] = useState(false);
  const text = a.answer_text || "";
  const sources = Array.isArray(a.cited_sources) ? a.cited_sources : [];
  const long = text.length > 280;

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-gray-900 px-1.5 py-0.5 text-xs font-medium text-white">{a.engine}</span>
        <SentimentBadge sentiment={a.sentiment} />
        {a.goal_alignment != null && (
          <span className="text-xs text-gray-500">goal {a.goal_alignment.toFixed(2)}</span>
        )}
        {a.mentions_contested && (
          <span className="rounded bg-red-50 px-1.5 py-0.5 text-xs text-red-700">contested</span>
        )}
        {a.surfaces_owned && (
          <span className="rounded bg-green-50 px-1.5 py-0.5 text-xs text-green-700">owned source</span>
        )}
        {a.persona && (
          <span className="text-xs text-gray-400">
            {a.persona}
            {a.location ? ` · ${a.location}` : ""}
          </span>
        )}
      </div>
      <div className="mt-2 text-sm font-medium text-gray-900">{a.prompt}</div>
      <p className="mt-1 whitespace-pre-wrap text-sm text-gray-700">
        {open || !long ? text : text.slice(0, 280) + "…"}
      </p>
      {long && (
        <button onClick={() => setOpen((o) => !o)} className="mt-1 text-xs text-blue-600 hover:underline">
          {open ? "Show less" : "Show more"}
        </button>
      )}
      {sources.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {sources.map((s, i) => (
            <span key={i} className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
              {typeof s === "string" ? s : JSON.stringify(s)}
            </span>
          ))}
        </div>
      )}
    </Card>
  );
}
