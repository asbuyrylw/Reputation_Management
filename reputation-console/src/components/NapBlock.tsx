"use client";

// Shared "business listing details (NAP)" block. NAP = Name, Address, Phone — the details
// that must match EXACTLY across every directory listing (a core local-SEO + AI-trust signal).
// Previously duplicated in seo-overview/page.tsx and content/outreach/page.tsx; this is the
// single definition both pages use.

import type { Nap } from "@/lib/types";

const NAP_LABELS: Record<string, string> = {
  name: "Business name",
  address: "Address",
  phone: "Phone",
  website: "Website",
  areas_served: "Areas served",
};

export function NapBlock({ nap, className = "" }: { nap: Nap; className?: string }) {
  const rows: { key: string; label: string; value: string | null }[] = [
    { key: "name", label: NAP_LABELS.name, value: nap.name },
    { key: "address", label: NAP_LABELS.address, value: nap.address },
    { key: "phone", label: NAP_LABELS.phone, value: nap.phone },
    { key: "website", label: NAP_LABELS.website, value: nap.website },
    { key: "areas_served", label: NAP_LABELS.areas_served, value: nap.areas_served },
  ];
  return (
    <div className={`rounded-lg bg-slate-50 p-3 ${className}`}>
      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Business listing details (Name, Address, Phone)
      </div>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
        {rows.map((r) => {
          const missing = nap.missing_fields.includes(r.key);
          return (
            <div key={r.key} className="flex items-baseline justify-between gap-2 text-xs">
              <dt className="text-slate-500">{r.label}</dt>
              <dd className={`text-right font-medium ${missing ? "text-amber-600" : "text-slate-700"}`}>
                {r.value || (missing ? "Missing — add this" : "—")}
              </dd>
            </div>
          );
        })}
      </dl>
      {nap.missing_fields.length > 0 && (
        <p className="mt-2 rounded-md bg-amber-50 px-2.5 py-1.5 text-[11px] text-amber-700 ring-1 ring-inset ring-amber-200">
          {nap.consistency_note ||
            "Fill in the highlighted fields so your name, address & phone match exactly across every directory — inconsistent listings hurt local SEO."}
        </p>
      )}
    </div>
  );
}
