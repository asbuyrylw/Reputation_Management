"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useBusiness } from "@/lib/business";
import {
  usePrompts, useAddPrompt, useUpdatePrompt, useDeletePrompt, useTriggerJob,
} from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import type { CustomPrompt } from "@/lib/types";

export default function PromptsPage() {
  const { businessId, canEdit } = useBusiness();
  const prompts = usePrompts(businessId);
  const add = useAddPrompt(businessId);
  const update = useUpdatePrompt(businessId);
  const del = useDeletePrompt(businessId);
  const suggest = useTriggerJob(businessId);
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [topic, setTopic] = useState("");

  if (prompts.isLoading) return <Spinner />;
  const rows = prompts.data ?? [];
  const enabled = rows.filter((r) => r.enabled);
  const suggestions = rows.filter((r) => r.source === "ai_suggested" && !r.enabled);
  const paused = rows.filter((r) => !r.enabled && r.source !== "ai_suggested");

  const runSuggest = () =>
    suggest.mutate(
      { jobType: "suggest_prompts" },
      { onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ["prompts", businessId] }), 12000) },
    );

  const Row = ({ p }: { p: CustomPrompt }) => (
    <div className="flex items-start justify-between gap-3 border-t border-gray-100 py-2.5 first:border-0">
      <div className="min-w-0">
        <p className="text-sm text-gray-900">{p.prompt}</p>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-gray-500">
          {p.topic && <span className="rounded bg-gray-100 px-1.5 py-0.5">{p.topic}</span>}
          {(p.tags || "")
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean)
            .map((t) => (
              <span key={t} className="text-gray-400">#{t}</span>
            ))}
          {p.source === "ai_suggested" && <span className="text-violet-600">AI-suggested</span>}
        </div>
      </div>
      {canEdit && (
        <div className="flex shrink-0 items-center gap-2">
          <button
            onClick={() => update.mutate({ id: p.id, enabled: !p.enabled })}
            className={`rounded-md px-2 py-1 text-xs font-medium ${
              p.enabled
                ? "border border-gray-300 text-gray-600 hover:bg-gray-100"
                : "bg-gray-900 text-white hover:bg-gray-700"
            }`}
          >
            {p.enabled ? "Tracking" : "Track"}
          </button>
          <button
            onClick={() => del.mutate(p.id)}
            className="text-gray-400 hover:text-rose-600"
            aria-label="delete"
          >
            ×
          </button>
        </div>
      )}
    </div>
  );

  return (
    <div>
      <PageHeader
        title="Prompts & topics"
        subtitle="The exact questions we ask the AI engines about you. Add your own — every tracked prompt flows through the audit, the gap analysis, the content plan, and the competitor benchmark."
      />

      {canEdit && (
        <Card className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-gray-600">Add a question your customers (or critics) would ask AI about you.</span>
            <button
              onClick={runSuggest}
              disabled={suggest.isPending}
              className="rounded-md border border-violet-300 bg-violet-50 px-3 py-1.5 text-sm font-medium text-violet-700 hover:bg-violet-100 disabled:opacity-50"
            >
              {suggest.isPending ? "Thinking…" : "Suggest prompts with AI"}
            </button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="e.g. Is Acme a pyramid scheme or a legitimate business?"
              className="min-w-[18rem] flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm"
            />
            <input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Topic (optional)"
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
            />
            <button
              onClick={() =>
                text.trim() &&
                add.mutate({ prompt: text, topic }, { onSuccess: () => { setText(""); setTopic(""); } })
              }
              disabled={add.isPending || !text.trim()}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-100 disabled:opacity-50"
            >
              Add prompt
            </button>
          </div>
          {add.isError && <p className="mt-2 text-xs text-rose-600">{(add.error as Error)?.message}</p>}
        </Card>
      )}

      {rows.length === 0 ? (
        <EmptyState
          title="No custom prompts yet"
          why="We're tracking the standard battery of questions about you. Add your own to measure the questions that matter most to your business."
          produces="Every prompt you add is measured across all the AI engines on the next audit, and feeds the gap analysis and content plan."
          timing="Prompts take effect on the next audit."
        />
      ) : (
        <div className="space-y-4">
          {suggestions.length > 0 && (
            <Card className="border-violet-200 bg-violet-50/40">
              <h3 className="text-sm font-semibold text-violet-900">
                AI-suggested ({suggestions.length}) — review and turn on the ones you want
              </h3>
              <div className="mt-1">
                {suggestions.map((p) => <Row key={p.id} p={p} />)}
              </div>
            </Card>
          )}
          <Card>
            <h3 className="text-sm font-semibold text-gray-900">
              Tracked prompts ({enabled.length})
            </h3>
            <p className="mt-0.5 text-xs text-gray-500">These run on every audit. Pause one to stop tracking it without deleting it.</p>
            {update.isError && <p className="mt-1 text-xs text-rose-600">{(update.error as Error)?.message}</p>}
            <div className="mt-2">
              {enabled.length === 0
                ? <p className="py-2 text-sm text-gray-400">None tracked yet — add one above, or enable a suggestion.</p>
                : enabled.map((p) => <Row key={p.id} p={p} />)}
            </div>
          </Card>

          {paused.length > 0 && (
            <Card>
              <h3 className="text-sm font-semibold text-gray-900">Paused ({paused.length})</h3>
              <p className="mt-0.5 text-xs text-gray-500">Not tracked right now. Click “Track” to include one in the next audit.</p>
              <div className="mt-2">{paused.map((p) => <Row key={p.id} p={p} />)}</div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
