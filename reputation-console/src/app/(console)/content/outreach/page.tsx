"use client";

import { useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useBusiness } from "@/lib/business";
import { useDiscoveryTargets, useTriggerJob, useAddDiscoveryTarget, useSetTargetStatus, useUpdateTargetContact, usePushTarget, useDraftPitch, useDirectoryCitations } from "@/lib/hooks";
import { Card, PageHeader, Spinner, Chip, Input, Button } from "@/components/ui";
import { SecHead } from "@/components/DashboardV2";
import { TableContainer, Th, Td } from "@/components/content/TableContainer";
import { ComplianceNotice } from "@/components/content/ComplianceNotice";
import { EmptyState } from "@/components/primitives";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import { NapBlock } from "@/components/NapBlock";
import type { Tone } from "@/lib/uiTokens";
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
      className="text-xs font-medium text-indigo hover:underline"
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

// "Get listed (directories)" — the NAP block (consistent name/address/phone) plus a curated
// list of high-authority directories to submit to. Consistent citations + listings on trusted
// directories are a core local-SEO + AI-trust signal.
function DirectoryCitationsSection({ data }: { data: DirectoryCitations | undefined }) {
  if (!data || data.directories.length === 0) return null;
  const { nap, directories, summary } = data;
  return (
    <Card className="mb-4">
      <SecHead
        title="Get listed (directories)"
        note={`${summary.essential} essential of ${summary.total} suggested`}
      />
      <p className="mx-0.5 -mt-1.5 mb-1 text-xs text-ink-3">
        Listings on trusted directories — with your name, address &amp; phone matching exactly everywhere — are a core
        local-SEO and AI-trust signal.
      </p>

      {/* NAP block — keep this identical on every directory you submit to (shared component) */}
      <NapBlock nap={nap} className="mt-3" />

      {/* curated directory rows */}
      <ul className="mt-3 divide-y divide-line">
        <Collapsible
          items={directories}
          noun="directories"
          toggleAs="li"
          toggleClassName="py-2"
          render={(d) => (
            <li key={d.key} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-ink-2">{d.name}</span>
                  {d.financial && <Chip tone="info">Financial</Chip>}
                  <Chip tone="neutral" className="capitalize">{d.category.replace(/_/g, " ")}</Chip>
                </div>
                <div className="text-[11px] text-ink-4">{d.authority} authority</div>
              </div>
              <a href={d.submit_url} target="_blank" rel="noreferrer"
                className="shrink-0 rounded-md border border-line-2 bg-white px-2.5 py-1 text-xs font-medium text-indigo hover:bg-paper">
                Open submission ↗
              </a>
            </li>
          )}
        />
      </ul>
      {data.note && <p className="mt-2 text-[11px] text-ink-4">{data.note}</p>}
    </Card>
  );
}

function matchLabel(s: number | null): { label: string; tone: Tone } {
  if (s == null) return { label: "—", tone: "neutral" };
  if (s >= 0.7) return { label: "High", tone: "good" };
  if (s >= 0.4) return { label: "Medium", tone: "info" };
  return { label: "Low", tone: "neutral" };
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
        <Input placeholder="Name" value={f.contact_name} onChange={(e) => setF({ ...f, contact_name: e.target.value })} className="px-1.5 py-0.5 text-xs" />
        <Input placeholder="Email" value={f.contact_email} onChange={(e) => setF({ ...f, contact_email: e.target.value })} className="px-1.5 py-0.5 text-xs" />
        <Input placeholder="Phone" value={f.contact_phone} onChange={(e) => setF({ ...f, contact_phone: e.target.value })} className="px-1.5 py-0.5 text-xs" />
        <div className="flex gap-1">
          <Button size="sm" onClick={() => update.mutate({ targetId: t.id, ...f }, { onSuccess: () => setEditing(false) })}>Save</Button>
          <button onClick={() => setEditing(false)} className="text-xs text-ink-3">Cancel</button>
        </div>
      </div>
    );
  }
  return (
    <div className="text-xs">
      {has ? (
        <>
          {t.contact_name && <div className="font-medium text-ink-2">{t.contact_name}</div>}
          {t.contact_email && <a href={`mailto:${t.contact_email}`} className="block text-indigo hover:underline">{t.contact_email}</a>}
          {t.contact_phone && <a href={`tel:${t.contact_phone}`} className="block text-ink-3">{t.contact_phone}</a>}
          {t.contact_verified === false && <div className="text-amber-600">unverified — confirm first</div>}
          {canEdit && <button onClick={() => setEditing(true)} className="mt-0.5 text-ink-4 hover:text-ink-2">edit</button>}
        </>
      ) : canEdit ? (
        <button onClick={() => setEditing(true)} className="text-indigo hover:underline">+ add contact</button>
      ) : (
        <span className="text-ink-4">—</span>
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
            <span className="text-sm text-ink-3">
              Targets are found automatically by the Discovery agent — or add your own.
            </span>
            <div className="flex gap-2">
              <Button
                onClick={runFind}
                loading={find.isPending}
              >
                {find.isPending ? "Finding…" : "Find targets"}
              </Button>
              <Button
                variant="secondary"
                onClick={() =>
                  enrich.mutate(
                    { jobType: "enrich_outreach" },
                    { onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ["discovery-targets", businessId] }), 12000) },
                  )
                }
                disabled={enrich.isPending || data.length === 0}
                title="Best-effort: auto-find public contacts for your targets (you confirm before sending)"
              >
                {enrich.isPending ? "Finding contacts…" : "Find contacts"}
              </Button>
              <Button
                variant="secondary"
                onClick={() => setShowAdd((s) => !s)}
              >
                {showAdd ? "Cancel" : "Add manually"}
              </Button>
            </div>
          </div>
          {showAdd && (
            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
              <Input placeholder="Name (journalist / outlet / podcast)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <Input placeholder="Outlet / publication" value={form.outlet} onChange={(e) => setForm({ ...form, outlet: e.target.value })} />
              <Input placeholder="URL" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
              <Input placeholder="Beat / topic they cover" value={form.beat} onChange={(e) => setForm({ ...form, beat: e.target.value })} />
              <Button
                onClick={() => form.name.trim() && add.mutate({ ...form, channel: "manual" }, { onSuccess: () => { setForm({ name: "", outlet: "", url: "", beat: "" }); setShowAdd(false); } })}
                disabled={add.isPending || !form.name.trim()}
                className="sm:w-32"
              >
                Add target
              </Button>
            </div>
          )}
        </Card>
      )}

      {data.some((t) => t.contact_verified === false) && (
        <ComplianceNotice tone="info" className="mb-4">
          ⚠ Some contacts were <span className="font-semibold">auto-found and are unverified</span>. Confirm the right
          person and address on the outlet&apos;s own site before reaching out — don&apos;t send to an unconfirmed contact.
        </ComplianceNotice>
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
          <Button variant="secondary" onClick={exportCsv}>Export CSV</Button>
        </div>
        <TableContainer>
            <thead>
              <tr>
                <Th>Name / outlet</Th>
                <Th>Type</Th>
                <Th>Helps with</Th>
                <Th>Contact</Th>
                <Th>Match</Th>
                <Th>Status</Th>
                {canEdit && <Th>Actions</Th>}
              </tr>
            </thead>
            <tbody>
              <Collapsible
                items={data}
                noun="targets"
                toggleAs="tr"
                colSpan={canEdit ? 7 : 6}
                render={(t) => (
                <tr key={t.id} className="hover:bg-paper">
                  <Td>
                    {t.url ? (
                      <a href={t.url} target="_blank" rel="noreferrer" className="font-medium text-indigo hover:underline">{t.name}</a>
                    ) : (
                      <span className="font-medium text-ink-2">{t.name}</span>
                    )}
                    {t.outlet && <div className="text-xs text-ink-3">{t.outlet}</div>}
                    {t.beat && <div className="text-[11px] text-ink-4">covers {t.beat}</div>}
                  </Td>
                  <Td className="text-xs text-ink-3">{(t.target_type ?? t.channel ?? "").replace(/_/g, " ")}</Td>
                  <Td>
                    {t.capabilities && t.capabilities.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {t.capabilities.slice(0, 4).map((c) => (
                          <Chip key={c} tone="info">{capLabel(c)}</Chip>
                        ))}
                      </div>
                    ) : (
                      <span className="text-xs text-ink-4">—</span>
                    )}
                  </Td>
                  <Td><ContactCell t={t} businessId={businessId} canEdit={canEdit} /></Td>
                  <Td><Chip tone={matchLabel(t.score).tone}>{matchLabel(t.score).label}</Chip></Td>
                  <Td>
                    {canEdit ? (
                      <select
                        value={t.status ?? "suggested"}
                        onChange={(e) => setStatus.mutate({ targetId: t.id, status: e.target.value })}
                        className="rounded border border-line px-1.5 py-0.5 text-xs"
                      >
                        {Object.entries(STATUS_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                      </select>
                    ) : (
                      STATUS_LABEL[t.status ?? "suggested"] ?? t.status
                    )}
                  </Td>
                  {canEdit && (
                    <Td>
                      <div className="flex flex-col gap-1">
                        <button onClick={() => draftPitch(t)} disabled={pitch.isPending}
                          className="rounded border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50">
                          {pitch.isPending ? "Drafting…" : "Draft pitch"}
                        </button>
                        <button onClick={() => push.mutate(t.id, { onSuccess: (r) => setPushed((s) => ({ ...s, [t.id]: r.sent })) })} disabled={push.isPending}
                          className="rounded border border-line px-2 py-0.5 text-[11px] text-ink-3 hover:bg-line disabled:opacity-50"
                          title="Send to your CRM/stack via webhook (needs WEBHOOK_URL)">
                          {pushed[t.id] === true ? "Sent ✓" : pushed[t.id] === false ? "Not configured" : "Push to CRM"}
                        </button>
                      </div>
                    </Td>
                  )}
                </tr>
                )}
              />
            </tbody>
        </TableContainer>
        </>
      )}

      {pitchModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4" onClick={() => setPitchModal(null)}>
          <div className="w-full max-w-lg rounded-2xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-bold text-ink">Draft pitch — {pitchModal.name}</h3>
            <textarea readOnly value={pitchModal.text} rows={10} className="mt-3 w-full rounded-md border border-line-2 px-3 py-2 text-sm" />
            <div className="mt-3 flex items-center justify-end gap-2">
              <Button variant="secondary" onClick={() => navigator.clipboard?.writeText(pitchModal.text)}>Copy</Button>
              <Button onClick={() => setPitchModal(null)}>Close</Button>
            </div>
            <p className="mt-2 text-xs text-ink-4">Review &amp; personalize before sending — confirm the contact on the outlet&apos;s own site.</p>
          </div>
        </div>
      )}
    </div>
  );
}
