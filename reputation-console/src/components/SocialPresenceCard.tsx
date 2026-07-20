"use client";

import { useState } from "react";
import { useSocialAudit, useAuditSocials, useSetSocialProfile } from "@/lib/hooks";
import { Card } from "@/components/ui";
import type { SocialAudit } from "@/lib/types";

// Pretty platform names for the badge/heading.
const PLATFORM_LABEL: Record<string, string> = {
  linkedin: "LinkedIn",
  facebook: "Facebook",
  instagram: "Instagram",
  x: "X",
  youtube: "YouTube",
  tiktok: "TikTok",
  pinterest: "Pinterest",
  reddit: "Reddit",
  gbp: "Google Business Profile",
};
const platformLabel = (p: string) =>
  PLATFORM_LABEL[p] ?? p.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

// How the profile was found -> a short, plain-English provenance note next to the "found" badge.
function sourceNote(source: string | null): string | null {
  if (source === "manual") return null; // shown as a "you confirmed" badge instead
  if (source === "website") return "confirmed (linked from your site)";
  if (source === "serper") return "Google Business Profile";
  if (source === "search") return "inferred from a web search";
  if (source === "citation") return "found in an AI answer";
  return null;
}

function PlatformRow({ a, canEdit, onSave, saving }: {
  a: SocialAudit; canEdit: boolean; onSave: (platform: string, url: string) => void; saving: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [url, setUrl] = useState(a.profile_url ?? "");
  const pct = a.completeness != null ? Math.round(a.completeness * 100) : null;
  const confirmed = a.source === "manual";
  const note = a.exists ? sourceNote(a.source) : null;
  const topRec = a.audit?.recommendations?.[0] ?? null;
  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-slate-900">{platformLabel(a.platform)}</span>
          {a.exists ? (
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">✓ found</span>
          ) : (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">✗ not found</span>
          )}
          {confirmed && <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[11px] font-semibold text-indigo-700">✓ you confirmed</span>}
          {a.exists && !confirmed && a.confidence === "ambiguous" && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-700" title="Two same-name profiles looked equally likely — confirm the right one below.">⚠ is this you?</span>
          )}
          {note && <span className="text-[11px] text-slate-400">{note}</span>}
        </div>
        <div className="flex items-center gap-2.5">
          {a.exists && a.profile_url && (
            <a href={a.profile_url} target="_blank" rel="noreferrer" className="text-[11px] font-medium text-indigo-600 hover:underline">View →</a>
          )}
          {canEdit && !editing && (
            <button type="button" onClick={() => { setUrl(a.profile_url ?? ""); setEditing(true); }} className="text-[11px] font-medium text-slate-400 hover:text-indigo-600 hover:underline">
              {a.exists ? "Not us? Fix →" : "Add URL →"}
            </button>
          )}
        </div>
      </div>

      {/* inline override: paste the correct profile URL — it sticks and re-audits won't overwrite it */}
      {editing && (
        <div className="mt-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={`https://…/${a.platform === "gbp" ? "your Google Business Profile" : a.platform}…`}
              className="min-w-[220px] flex-1 rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-800 focus:border-indigo-400 focus:outline-none"
            />
            <button type="button" onClick={() => { onSave(a.platform, url.trim()); setEditing(false); }} disabled={saving}
              className="rounded-md bg-indigo-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50">Save</button>
            <button type="button" onClick={() => setEditing(false)} className="rounded-md border border-slate-300 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50">Cancel</button>
          </div>
          <p className="mt-1 text-[10px] text-slate-400">Paste the exact URL of the profile you run. It&apos;s marked confirmed, so future audits won&apos;t change it.</p>
        </div>
      )}

      {/* completeness bar + % (only when we have a profile to measure) */}
      {a.exists && pct != null && !editing && (
        <div className="mt-1.5 flex items-center gap-2">
          <div className="h-1.5 w-full max-w-[180px] overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
          </div>
          <span className="text-[11px] text-slate-500">{pct}% complete</span>
        </div>
      )}

      {/* the single most actionable next step */}
      {topRec && !editing && (
        <div className="mt-1 text-[11px] text-slate-600">
          <span className="font-medium text-slate-500">Next:</span> {topRec}
        </div>
      )}
    </li>
  );
}

// "Social presence" — per-platform existence/ownership + completeness + the top recommendation,
// with an "Audit socials" button that re-checks the profiles and a per-row override so the owner
// can correct a wrong same-name page (it sticks — future audits won't overwrite a confirmed URL).
export function SocialPresenceCard({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const { data, isLoading } = useSocialAudit(businessId);
  const audit = useAuditSocials(businessId);
  const setProfile = useSetSocialProfile(businessId);

  const platforms = data ?? [];
  // Nothing to show and not loading -> render nothing rather than an empty shell.
  if (!isLoading && platforms.length === 0 && !canEdit) return null;

  const found = platforms.filter((p) => p.exists).length;

  return (
    <Card padded={false}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Social presence</h3>
          {platforms.length > 0 && (
            <p className="text-[11px] text-slate-400">{found} of {platforms.length} profiles found</p>
          )}
        </div>
        {canEdit && (
          <div className="flex flex-col items-end gap-0.5">
            <button
              type="button"
              onClick={() => audit.mutate()}
              disabled={audit.isPending}
              className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {audit.isPending && (
                <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                </svg>
              )}
              {audit.isPending ? "Queuing…" : audit.isSuccess ? "Queued ✓ — refreshing" : "Audit socials"}
            </button>
            <span className="text-[10px] text-slate-400">Re-checks your profiles. Confirmed URLs are kept.</span>
          </div>
        )}
      </div>

      <div className="px-4 py-3">
        {isLoading ? (
          <p className="text-xs text-slate-400">Loading…</p>
        ) : platforms.length === 0 ? (
          <p className="text-xs text-slate-500">No social audit yet. Click “Audit socials” to check your profiles.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {platforms.map((a) => (
              <PlatformRow
                key={a.platform}
                a={a}
                canEdit={canEdit}
                saving={setProfile.isPending}
                onSave={(platform, profile_url) => setProfile.mutate({ platform, profile_url })}
              />
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
