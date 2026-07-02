"use client";

import { useState } from "react";
import { useBusiness } from "@/lib/business";
import {
  useApprovalQueue,
  useApproveQueueItem,
  useRejectQueueItem,
  useEditReviewReply,
} from "@/lib/hooks";
import { Card, PageHeader, Spinner, Pill, Chip, Button } from "@/components/ui";
import { TabNav } from "@/components/content/TabNav";
import { EmptyState } from "@/components/primitives";
import { ApiError } from "@/lib/api";
import type { QueueItem, QueueItemKind } from "@/lib/types";

const KIND_LABELS: Record<QueueItemKind, string> = {
  mention_reply: "Mention reply",
  review_reply: "Review reply",
  scheduled_post: "Scheduled post",
};

// Compliance badge: false = blocked (Approve disabled), null = needs a human look (allowed), true = clear.
function ComplianceBadge({ pass }: { pass: boolean | null }) {
  if (pass === false) return <Pill tone="bad">Compliance flagged</Pill>;
  if (pass === null) return <Pill tone="info">Needs human review</Pill>;
  return <Pill tone="good">Compliance clear</Pill>;
}

function Stars({ rating }: { rating: number }) {
  return <span className="text-amber-500">{"★".repeat(Math.max(0, Math.min(5, Math.round(rating))))}</span>;
}

function QueueItemCard({ item, businessId }: { item: QueueItem; businessId: number | null }) {
  const approve = useApproveQueueItem(businessId);
  const reject = useRejectQueueItem(businessId);
  const editReview = useEditReviewReply(businessId);

  const [editing, setEditing] = useState(false);
  const [draftText, setDraftText] = useState(item.draft ?? "");
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const flags = item.compliance.flags ?? [];
  const blocked = item.compliance.pass === false;
  const approvable = item.kind === "mention_reply" || item.kind === "review_reply";

  const doApprove = (confirmMsg?: string) => {
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    setErr(null);
    approve.mutate(
      { kind: item.kind, itemId: item.id },
      { onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't approve — try again.") },
    );
  };
  const doReject = () => {
    setErr(null);
    reject.mutate(
      { kind: item.kind, itemId: item.id },
      { onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't update — try again.") },
    );
  };
  const saveEdit = () => {
    setErr(null);
    editReview.mutate(
      { id: item.id, draft: draftText },
      {
        onSuccess: () => setEditing(false),
        onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't save the edit."),
      },
    );
  };
  const copyDraft = async () => {
    try {
      await navigator.clipboard.writeText(item.draft ?? "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <Card>
      {/* header row */}
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="neutral">{KIND_LABELS[item.kind]}</Pill>
        {item.capability === "alert_only" && <Pill tone="info">Alert only</Pill>}
        <Chip tone={item.surface === "owned" ? "good" : "info"}>
          {item.surface === "owned" ? "You own this" : "Third-party"}
        </Chip>
        <ComplianceBadge pass={item.compliance.pass} />
        {item.source && <span className="text-xs text-ink-4">{item.source}</span>}
        {item.rating != null && <Stars rating={item.rating} />}
        {item.scheduled_for && (
          <span className="ml-auto text-xs text-ink-4">scheduled {new Date(item.scheduled_for).toLocaleString()}</span>
        )}
      </div>

      {/* the thing being replied to */}
      {item.title && <div className="mt-2 text-sm font-semibold text-ink">{item.title}</div>}

      {/* draft */}
      {item.kind === "review_reply" || item.kind === "mention_reply" ? (
        editing ? (
          <textarea
            value={draftText}
            onChange={(e) => setDraftText(e.target.value)}
            rows={4}
            className="mt-2 w-full rounded-md border border-line-2 px-3 py-2 text-sm"
          />
        ) : (
          <p className="mt-2 whitespace-pre-wrap rounded-lg bg-paper p-3 text-sm text-ink-2">
            {item.draft || <span className="text-ink-4">No draft text.</span>}
          </p>
        )
      ) : (
        <p className="mt-2 whitespace-pre-wrap rounded-lg bg-paper p-3 text-sm text-ink-2">
          {item.draft || <span className="text-ink-4">No draft text.</span>}
        </p>
      )}

      {flags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {flags.map((f, i) => (
            <Chip key={i} tone="bad">{f}</Chip>
          ))}
        </div>
      )}

      {/* actions, branched on capability */}
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3">
        {item.capability === "alert_only" ? (
          <>
            {item.url && (
              <a
                href={item.url}
                target="_blank"
                rel="noreferrer"
                className="rounded-lg bg-ink px-3 py-1.5 text-sm font-medium text-white hover:bg-ink-2"
              >
                Open on platform →
              </a>
            )}
            <Button variant="secondary" size="sm" onClick={copyDraft}>
              {copied ? "Copied" : "Copy draft"}
            </Button>
            <Button variant="secondary" size="sm" onClick={doReject} disabled={reject.isPending}>
              Dismiss
            </Button>
            <p className="w-full text-xs text-ink-3">
              This platform&apos;s terms require you to post manually — paste the draft yourself. You&apos;re responsible
              for what goes live here.
            </p>
          </>
        ) : item.capability === "review_reply" ? (
          <>
            {editing ? (
              <>
                <Button size="sm" onClick={saveEdit} disabled={editReview.isPending}>
                  {editReview.isPending ? "Saving…" : "Save edit"}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => { setEditing(false); setDraftText(item.draft ?? ""); }}
                >
                  Cancel
                </Button>
              </>
            ) : (
              <>
                <button
                  onClick={() => doApprove("This reply will be posted publicly on the review. Approve?")}
                  disabled={blocked || approve.isPending}
                  title={blocked ? "Resolve the compliance flags before approving." : undefined}
                  className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {approve.isPending ? "Approving…" : "Approve & post"}
                </button>
                <Button variant="secondary" size="sm" onClick={doReject} disabled={reject.isPending}>
                  Reject
                </Button>
                {item.editable && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => { setEditing(true); setDraftText(item.draft ?? ""); }}
                  >
                    Edit
                  </Button>
                )}
              </>
            )}
          </>
        ) : item.capability === "publish" || item.capability === "publish_costed" ? (
          approvable ? (
            <>
              <button
                onClick={() => doApprove("This will be published. Approve?")}
                disabled={blocked || approve.isPending}
                title={blocked ? "Resolve the compliance flags before approving." : undefined}
                className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {approve.isPending ? "Approving…" : "Approve & publish"}
              </button>
              <Button variant="secondary" size="sm" onClick={doReject} disabled={reject.isPending}>
                Reject
              </Button>
            </>
          ) : (
            // scheduled_post — read-only status
            <span className="text-xs text-ink-3">
              Status: <span className="font-medium text-ink-2">{item.status || "scheduled"}</span> — managed automatically.
            </span>
          )
        ) : (
          <span className="text-xs text-ink-3">
            Status: <span className="font-medium text-ink-2">{item.status || "—"}</span>
          </span>
        )}
      </div>

      {err && <p className="mt-2 text-xs text-alert">{err}</p>}
    </Card>
  );
}

type KindFilter = "all" | QueueItemKind;

export default function ApprovalsPage() {
  const { businessId } = useBusiness();
  const [kind, setKind] = useState<KindFilter>("all");
  const { data, isLoading } = useApprovalQueue(businessId, undefined, kind === "all" ? undefined : kind);

  if (isLoading || !data) return <Spinner />;

  const items = data.items ?? [];

  const FILTERS: { key: KindFilter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "review_reply", label: "Review replies" },
    { key: "mention_reply", label: "Mention replies" },
    { key: "scheduled_post", label: "Scheduled posts" },
  ];

  return (
    <div>
      <PageHeader
        title="Needs your approval"
        subtitle="One inbox for everything waiting on you — review replies, mention replies, and scheduled posts. Approving an owned-surface item publishes it; third-party items are draft-only, so you post those yourself."
      />

      <TabNav
        className="mb-4"
        tabs={FILTERS}
        active={kind}
        onSelect={(k) => setKind(k as KindFilter)}
      />

      {items.length === 0 ? (
        <EmptyState
          title="Nothing waiting on you"
          why="When a review reply, mention reply, or scheduled post is drafted and screened for compliance, it lands here for your sign-off."
          produces="You'll approve owned-surface items to publish them, or copy third-party drafts to post manually."
          cta={{ label: "Manage connections", href: "/integrations" }}
        />
      ) : (
        <div className="space-y-3">
          {items.map((it) => (
            <QueueItemCard key={`${it.kind}-${it.id}`} item={it} businessId={businessId} />
          ))}
        </div>
      )}
    </div>
  );
}
