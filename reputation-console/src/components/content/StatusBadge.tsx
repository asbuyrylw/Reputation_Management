// One status chip for the whole content pipeline — maps every draft/asset/queue status word to a
// single semantic tone so statuses read consistently (published = good, needs-fix = bad, waiting =
// info, everything else neutral). Replaces the ad-hoc inline `bg-*-100 text-*-800` badges.

import { Chip } from "@/components/ui";
import type { Tone } from "@/lib/uiTokens";

const STATUS_WORDS: Record<string, string> = {
  pending_review: "Waiting for you",
  needs_fix: "Needs a fix",
  held: "Held — needs an author",
  approved: "Approved",
  rejected: "Rejected",
  published: "Published",
  live: "Live",
  drafted: "Drafted",
  scheduled: "Scheduled",
  failed: "Failed",
  skipped: "Skipped",
  new: "New",
};

export function statusTone(status: string): Tone {
  const s = (status || "").toLowerCase();
  if (["published", "live", "approved", "verified", "done", "sent"].includes(s)) return "good";
  if (["needs_fix", "held", "rejected", "failed", "error", "breached"].includes(s)) return "bad";
  if (["pending_review", "new", "drafted", "scheduled", "waiting", "in_review"].includes(s)) return "info";
  return "neutral";
}

export function StatusBadge({ status, className = "" }: { status: string; className?: string }) {
  return (
    <Chip tone={statusTone(status)} className={className}>
      {STATUS_WORDS[(status || "").toLowerCase()] ?? (status || "").replace(/_/g, " ")}
    </Chip>
  );
}
