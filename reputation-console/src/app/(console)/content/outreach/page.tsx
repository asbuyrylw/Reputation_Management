"use client";

import { useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useBusiness } from "@/lib/business";
import { useDiscoveryTargets, useTriggerJob, useAddDiscoveryTarget, useSetTargetStatus, useUpdateTargetContact, usePushTarget, useDraftPitch, useDirectoryCitations } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import type { DiscoveryTarget, DirectoryCitations } from "@/lib/types";

// How many items each long list shows before collapsing.
const COLLAPSE_AFTER = 5;

// Renders only the first `limit` of `items` by default, with a "See more / See less" toggle.
// Keeps long lists/tables short by default without changing how each row is rendered. The
// toggle is wrapped in `toggleAs` (default <div>) so it stays valid HTML inside a <ul>/<table>
// — e.g. pass "li" inside a <ul> or "tr" (with a render that returns a <td colSpan>) elsewhere.
function Collapsible<T>({ items, limit = COLLAPSE_AFTER, render, noun = "more", toggleAs = "div", toggleClassName = "", colSpan }: {
  items: T[];
  limit?: number;
  render: (item: T, index: number) => ReactNode;
  noun?: string;
  toggleAs?: "div" | "li" | "tr";
  toggleClassName?: string;
  colSpan?: number; // required when toggleAs="tr" so the toggle row spans the table
}) {
  const [expanded, setExpanded] = useState(false);
  const hidden = items.length - limit;
  const shown = expanded ? items : items.slice(0, limit);
  const button = (
    <button
      type="button"
      onClick={() => setExpanded((e) => !e)}
      className="text-xs font-medium text-indigo-600 hover:underline"
    >
      {expanded ? "See less" : `See more (${hidden} ${noun})`}
    </button>
  );
  return (
    <>
      {shown.map((item, i) => render(item, i))}
      {hidden > 0 && (
        toggleAs === "tr" ? (
          <tr className={toggleClassName}><td colSpan={colSpan} className="px-3 py-2">{button}</td></tr>
        ) : toggleAs === "li" ? (
          <li className={toggleClassName}>{button}</li>
        ) : (
          <div className={toggleClassName}>{button}</div>
        )
      )}
    </>
  );
}

const NAP_DIR_LABELS: Record<string, string> = {
  name: "Business name",
  address: "Address",
  phone: "Phone",
  website: "Website",
  areas_served: "Areas served",
};

// "Get listed (directories)" — the NAP block (consistent name/address/phone) plus a curated
// list of high-authority directories to submit to. Consistent citations + listings on trusted
// directories are a core local-SEO + AI-trust signal.
function DirectoryCitationsSection({ data }: { data: DirectoryCitations | undefined }) {
  if (!data || data.directories.length === 0) return null;
  const { nap, directories, summary } = data;
  const napRows: { key: string; label: string; value: string | null }[] = [
    { key: "name", label: NAP_DIR_LABELS.name, value: nap.name },
    { key: "address", label: NAP_DIR_LABELS.address, value: nap.address },
    { key: "phone", label: NAP_DIR_LABELS.phone, value: nap.phone },
    { key: "website", label: NAP_DIR_LABELS.website, value: nap.website },
    { key: "areas_served", label: NAP_DIR_LABELS.areas_served, value: nap.areas_served },
  ];
  return (
    <Card className="mb-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-slate-900">Get listed (directories)</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Listings on trusted directories — with your name, address &amp; phone matching exactly everywhere — are a core
            local-SEO and AI-trust signal. {summary.essential} essential of {summary.total} suggested.
          </p>
        </div>
      </div>

      {/* NAP block — keep this identical on every directory you submit to */}
      <div className="mt-3 rounded-lg bg-slate-50 p-3">
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Use these exact details (NAP)</div>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
          {napRows.map((r) => {
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
            {nap.consistency_note || "Fill in the highlighted fields so your listing is consistent across every directory."}
          </p>
        )}
      </div>

      {/* curated directory rows */}
      <ul className="mt-3 divide-y divide-slate-100">
        <Collapsible
          items={directories}
          noun="directories"
          toggleAs="li"
          toggleClassName="py-2"
          render={(d) => (
            <li key={d.key} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-slate-800">{d.name}</span>
                  {d.financial && <span className="rounded-full bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-700">Financial</span>}
                  <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] capitalize text-slate-500">{d.category.replace(/_/g, " ")}</span>
                </div>
                <div className="text-[11px] text-slate-400">{d.authority} authority</div>
              </div>
              <a href={d.submit_url} target="_blank" rel="noreferrer"
                className="shrink-0 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-indigo-600 hover:bg-slate-50">
                Open submission ↗
              </a>
            </li>
          )}
        />
      </ul>
      {data.note && <p className="mt-2 text-[11px] text-slate-400">{data.note}</p>}
    </Card>
  );
}

function matchLabel(s: number | null): { label: string; cls: string } {
  if (s == null) return { label: "—", cls: "text-slate-400" };
  if (s >= 0.7) return { label: "High", cls: "text-emerald-700" };
  if (s >= 0.4) return { label: "Medium", cls: "text-amber-700" };
  return { label: "Low", cls: "text-slate-500" };
}

const STATUS_LABEL: Record<string, string> = {
  suggested: "Suggested",
  contacted: "Contacted",
  responded: "Responded",
  declined: "Declined",
};

const CAP_LABEL: Record<string, string> = {
  earned_links: "Earned links",
  third_party_article: "Articles",
  press_mention: "Press",
  podcast_guesting: "Podcast",
  reviews: "Reviews",
  video: "Video",
  social_amplification: "Social",
  directory_listing: "Directory",
};
const capLabel = (c: string) => CAP_LABEL[c] ?? c.replace(/_/g, " ");

// Contact cell: shows name/email/phone (clickable) or an inline editor. Auto-found contacts are
// marked "unverified — confirm before sending" until a human enters/edits them.
function ContactCell({ t, businessId, canEdit }: { t: DiscoveryTarget; businessId: number | null; canEdit: boolean }) {
  const update = useUpdateTargetContact(businessId);
  const [editing, setEditing] = useState(false);
  const [f, setF] = useState({ contact_name: t.contact_name ?? "", contact_email: t.contact_email ?? "", contact_phone: t.contact_phone ?? "" });
  const has = t.contact_name || t.contact_email || t.contact_phone;

  if (editing) {
    return (
      <div className="space-y-1">
        <input placeholder="Name" value={f.contact_name} onChange={(e) => setF({ ...f, contact_name: e.target.value })} className="w-full rounded border border-slate-300 px-1.5 py-0.5 text-xs" />
        <input placeholder="Email" value={f.contact_email} onChange={(e) => setF({ ...f, contact_email: e.target.value })} className="w-full rounded border border-slate-300 px-1.5 py-0.5 text-xs" />
        <input placeholder="Phone" value={f.contact_phone} onChange={(e) => setF({ ...f, contact_phone: e.target.value })} className="w-full rounded border border-slate-300 px-1.5 py-0.5 text-xs" />
        <div className="flex gap-1">
          <button onClick={() => update.mutate({ targetId: t.id, ...f }, { onSuccess: () => setEditing(false) })} className="rounded bg-slate-900 px-2 py-0.5 text-xs text-white">Save</button>
          <button onClick={() => setEditing(false)} className="text-xs text-slate-500">Cancel</button>
        </div>
      </div>
    );
  }
  return (
    <div className="text-xs">
      {has ? (
        <>
          {t.contact_name && <div className="font-medium text-slate-700">{t.contact_name}</div>}
          {t.contact_email && <a href={`mailto:${t.contact_email}`} className="block text-indigo-600 hover:underline">{t.contact_email}</a>}
          {t.contact_phone && <a href={`tel:${t.contact_phone}`} className="block text-slate-600">{t.contact_phone}</a>}
          {t.contact_verified === false && <div className="text-amber-600">unverified — confirm first</div>}
          {canEdit && <button onClick={() => setEditing(true)} className="mt-0.5 text-slate-400 hover:text-slate-600">edit</button>}
        </>
      ) : canEdit ? (
        <button onClick={() => setEditing(true)} className="text-indigo-600 hover:underline">+ add contact</button>
      ) : (
        <span className="text-slate-400">—</span>
      )}
    </div>
  );
}

export default function OutreachPage() {
  const { businessId, canEdit } = useBusiness();
  const { data, isLoading } = useDiscoveryTargets(businessId);
  const find = useTriggerJob(businessId);
  const enrich = useTriggerJob(businessId);
  const add = useAddDiscoveryTarget(businessId);
  const setStatus = useSetTargetStatus(businessId);
  const push = usePushTarget(businessId);
  const pitch = useDraftPitch(businessId);
  const directories = useDirectoryCitations(businessId);
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: "", outlet: "", url: "", beat: "" });
  const [pitchModal, setPitchModal] = useState<{ name: string; text: string } | null>(null);
  const [pushed, setPushed] = useState<Record<number, boolean>>({});

  if (isLoading || !data) return <Spinner />;

  const runFind = () =>
    find.mutate(
      { jobType: "discovery" },
      { onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ["discovery-targets", businessId] }), 10000) },
    );

  const exportCsv = () => {
    const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const cols = ["name", "outlet", "url", "beat", "target_type", "contact_name", "contact_email", "contact_phone", "score", "status"];
    const rows = [cols.join(",")].concat(
      (data ?? []).map((t) => cols.map((c) => esc((t as unknown as Record<string, unknown>)[c])).join(",")),
    );
    const blob = new Blob([rows.join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "outreach_targets.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const draftPitch = (t: DiscoveryTarget) =>
    pitch.mutate(t.id, { onSuccess: (r) => setPitchModal({ name: t.name ?? "target", text: r.pitch }) });

  return (
    <div>
      <PageHeader
        title="Outreach targets"
        subtitle="Journalists, outlets, and communities worth pitching — earning a mention from them builds the outside proof AI trusts."
      />

      <JobProgressBanner businessId={businessId} className="mb-4" />

      <DirectoryCitationsSection data={directories.data} />

      {canEdit && (
        <Card className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-slate-600">
              Targets are found automatically by the Discovery agent — or add your own.
            </span>
            <div className="flex gap-2">
              <button
                onClick={runFind}
                disabled={find.isPending}
                className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
              >
                {find.isPending ? "Finding…" : "Find targets"}
              </button>
              <button
                onClick={() =>
                  enrich.mutate(
                    { jobType: "enrich_outreach" },
                    { onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ["discovery-targets", businessId] }), 12000) },
                  )
                }
                disabled={enrich.isPending || data.length === 0}
                title="Best-effort: auto-find public contacts for your targets (you confirm before sending)"
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
              >
                {enrich.isPending ? "Finding contacts…" : "Find contacts"}
              </button>
              <button
                onClick={() => setShowAdd((s) => !s)}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100"
              >
                {showAdd ? "Cancel" : "Add manually"}
              </button>
            </div>
          </div>
          {showAdd && (
            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
              <input placeholder="Name (journalist / outlet / podcast)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
              <input placeholder="Outlet / publication" value={form.outlet} onChange={(e) => setForm({ ...form, outlet: e.target.value })} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
              <input placeholder="URL" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
              <input placeholder="Beat / topic they cover" value={form.beat} onChange={(e) => setForm({ ...form, beat: e.target.value })} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
              <button
                onClick={() => form.name.trim() && add.mutate({ ...form, channel: "manual" }, { onSuccess: () => { setForm({ name: "", outlet: "", url: "", beat: "" }); setShowAdd(false); } })}
                disabled={add.isPending || !form.name.trim()}
                className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 sm:w-32"
              >
                Add target
              </button>
            </div>
          )}
        </Card>
      )}

      {data.some((t) => t.contact_verified === false) && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          ⚠ Some contacts were <span className="font-semibold">auto-found and are unverified</span>. Confirm the right
          person and address on the outlet&apos;s own site before reaching out — don&apos;t send to an unconfirmed contact.
        </div>
      )}

      {data.length === 0 ? (
        <EmptyState
          title="No outreach targets yet"
          why="These are people and outlets to pitch so they write about you — the third-party proof AI trusts."
          produces="Click “Find targets” to have the Discovery agent search for relevant journalists, outlets, podcasts, and communities — or add your own."
          timing="Finding targets takes a moment."
        />
      ) : (
        <>
        <div className="mb-2 flex justify-end">
          <button onClick={exportCsv} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100">Export CSV</button>
        </div>
        <Card className="overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">Name / outlet</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Helps with</th>
                <th className="px-3 py-2">Contact</th>
                <th className="px-3 py-2">Match</th>
                <th className="px-3 py-2">Status</th>
                {canEdit && <th className="px-3 py-2">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              <Collapsible
                items={data}
                noun="targets"
                toggleAs="tr"
                colSpan={canEdit ? 7 : 6}
                render={(t) => (
                <tr key={t.id} className="align-top hover:bg-slate-50">
                  <td className="px-3 py-2">
                    {t.url ? (
                      <a href={t.url} target="_blank" rel="noreferrer" className="font-medium text-indigo-600 hover:underline">{t.name}</a>
                    ) : (
                      <span className="font-medium text-slate-800">{t.name}</span>
                    )}
                    {t.outlet && <div className="text-xs text-slate-500">{t.outlet}</div>}
                    {t.beat && <div className="text-[11px] text-slate-400">covers {t.beat}</div>}
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-600">{(t.target_type ?? t.channel ?? "").replace(/_/g, " ")}</td>
                  <td className="px-3 py-2">
                    {t.capabilities && t.capabilities.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {t.capabilities.slice(0, 4).map((c) => (
                          <span key={c} className="rounded-full bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-700">{capLabel(c)}</span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2"><ContactCell t={t} businessId={businessId} canEdit={canEdit} /></td>
                  <td className={`px-3 py-2 font-medium ${matchLabel(t.score).cls}`}>{matchLabel(t.score).label}</td>
                  <td className="px-3 py-2">
                    {canEdit ? (
                      <select
                        value={t.status ?? "suggested"}
                        onChange={(e) => setStatus.mutate({ targetId: t.id, status: e.target.value })}
                        className="rounded border border-slate-200 px-1.5 py-0.5 text-xs"
                      >
                        {Object.entries(STATUS_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                      </select>
                    ) : (
                      STATUS_LABEL[t.status ?? "suggested"] ?? t.status
                    )}
                  </td>
                  {canEdit && (
                    <td className="px-3 py-2">
                      <div className="flex flex-col gap-1">
                        <button onClick={() => draftPitch(t)} disabled={pitch.isPending}
                          className="rounded border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50">
                          {pitch.isPending ? "Drafting…" : "Draft pitch"}
                        </button>
                        <button onClick={() => push.mutate(t.id, { onSuccess: (r) => setPushed((s) => ({ ...s, [t.id]: r.sent })) })} disabled={push.isPending}
                          className="rounded border border-slate-200 px-2 py-0.5 text-[11px] text-slate-600 hover:bg-slate-100 disabled:opacity-50"
                          title="Send to your CRM/stack via webhook (needs WEBHOOK_URL)">
                          {pushed[t.id] === true ? "Sent ✓" : pushed[t.id] === false ? "Not configured" : "Push to CRM"}
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
                )}
              />
            </tbody>
          </table>
        </Card>
        </>
      )}

      {pitchModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={() => setPitchModal(null)}>
          <div className="w-full max-w-lg rounded-2xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-bold text-slate-900">Draft pitch — {pitchModal.name}</h3>
            <textarea readOnly value={pitchModal.text} rows={10} className="mt-3 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <div className="mt-3 flex items-center justify-end gap-2">
              <button onClick={() => navigator.clipboard?.writeText(pitchModal.text)} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100">Copy</button>
              <button onClick={() => setPitchModal(null)} className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700">Close</button>
            </div>
            <p className="mt-2 text-xs text-slate-400">Review &amp; personalize before sending — confirm the contact on the outlet&apos;s own site.</p>
          </div>
        </div>
      )}
    </div>
  );
}
