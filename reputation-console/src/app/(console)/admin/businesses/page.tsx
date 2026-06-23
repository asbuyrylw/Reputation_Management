"use client";

import { useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useCreateBusiness, useUpdateBusiness, useDeleteBusiness } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { TagInput } from "@/components/TagInput";
import type { Business } from "@/lib/types";

// "Areas served" replaces the jargon "Geo" everywhere user-facing; the DB column stays `geo`.
// services is rendered as a multi-tag input (handled separately), not in this generic grid.
const FIELDS: [string, string][] = [
  ["name", "Name"],
  ["domain", "Domain"],
  ["industry", "Industry (e.g. Financial services)"],
  ["goal", "Goal"],
  ["contested_terms", "Contested terms (comma-separated)"],
  ["geo", "Areas served"],
];
const EMPTY: Record<string, string> = {
  name: "", domain: "", industry: "", goal: "", contested_terms: "", geo: "", services: "",
};

// plain-input fields shown in the inline editor (services + industry handled specially below)
const EDIT_FIELDS: [keyof Business, string][] = [
  ["name", "Name"],
  ["domain", "Domain"],
  ["industry", "Industry"],
  ["geo", "Areas served"],
  ["goal", "Goal"],
  ["contested_terms", "Contested terms"],
];

export default function AdminBusinessesPage() {
  const { businesses, loading } = useBusiness();
  const create = useCreateBusiness();
  const update = useUpdateBusiness();
  const [form, setForm] = useState<Record<string, string>>(EMPTY);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<Record<string, string>>({});
  const [deleting, setDeleting] = useState<Business | null>(null);
  // The delete hook is parameterized by id; recreating it as `deleting` changes targets the row.
  const del = useDeleteBusiness(deleting?.id ?? null);

  if (loading) return <Spinner />;

  const startEdit = (b: Business) => {
    setEditingId(b.id);
    setEditForm({
      name: b.name ?? "",
      domain: b.domain ?? "",
      industry: b.industry ?? "",
      geo: b.geo ?? "",
      goal: b.goal ?? "",
      contested_terms: b.contested_terms ?? "",
      services: b.services ?? "",
    });
  };
  const saveEdit = () => {
    if (editingId == null) return;
    update.mutate({ id: editingId, ...editForm }, { onSuccess: () => setEditingId(null) });
  };
  const confirmDelete = () => {
    if (!deleting) return;
    del.mutate(undefined, { onSuccess: () => setDeleting(null) });
  };

  return (
    <div>
      <PageHeader
        eyebrow="Admin"
        title="Businesses"
        subtitle="The businesses the engine tracks. Set one up with the guided wizard, add a bare record manually, or edit/remove an existing one."
      />

      {/* Guided setup — the recommended path: captures the full profile and runs everything. */}
      <Link
        href="/onboarding"
        className="mb-4 flex items-center justify-between gap-4 rounded-2xl bg-linear-to-r from-indigo-600 to-violet-600 p-5 text-white shadow-md shadow-indigo-500/20 transition hover:shadow-lg"
      >
        <div>
          <div className="text-base font-bold tracking-tight">Set up a new business</div>
          <div className="mt-0.5 text-sm text-indigo-100">
            Guided wizard — capture goals, competitors, areas served &amp; keywords, then run the full pipeline automatically.
          </div>
        </div>
        <span className="shrink-0 rounded-xl bg-white/15 px-4 py-2 text-sm font-semibold ring-1 ring-inset ring-white/30">
          Start setup →
        </span>
      </Link>

      <Card className="mb-4">
        <div className="mb-2 text-sm font-medium text-slate-700">Or add a business manually</div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {FIELDS.map(([k, label]) => (
            <input
              key={k}
              placeholder={label}
              value={form[k]}
              onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          ))}
        </div>
        <div className="mt-2">
          <label className="text-xs font-medium text-slate-500">Services (add several — e.g. financial services, financial advisors, life insurance, 401k)</label>
          <TagInput
            className="mt-1"
            value={form.services}
            onChange={(v) => setForm((f) => ({ ...f, services: v }))}
            placeholder="Type a service and press Enter"
          />
        </div>
        <button
          disabled={create.isPending || !form.name}
          onClick={() => create.mutate(form as { name: string }, { onSuccess: () => setForm(EMPTY) })}
          className="mt-3 rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          Create
        </button>
        {create.isError && <p className="mt-2 text-xs text-amber-700">Could not create the business.</p>}
      </Card>

      <Card className="overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">Domain</th>
              <th className="px-4 py-2">Areas served</th>
              <th className="px-4 py-2">Goal</th>
              <th className="px-4 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {businesses.map((b) =>
              editingId === b.id ? (
                <tr key={b.id} className="bg-indigo-50/40">
                  <td colSpan={5} className="px-4 py-3">
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      {EDIT_FIELDS.map(([k, label]) => (
                        <label key={String(k)} className="text-xs text-slate-500">
                          {label}
                          <input
                            value={editForm[k as string] ?? ""}
                            onChange={(e) => setEditForm((f) => ({ ...f, [k as string]: e.target.value }))}
                            className="mt-0.5 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-900"
                          />
                        </label>
                      ))}
                      <label className="text-xs text-slate-500 sm:col-span-2">
                        Services
                        <TagInput
                          className="mt-0.5"
                          value={editForm.services ?? ""}
                          onChange={(v) => setEditForm((f) => ({ ...f, services: v }))}
                          placeholder="Type a service and press Enter"
                        />
                      </label>
                    </div>
                    <div className="mt-3 flex items-center gap-2">
                      <button
                        onClick={saveEdit}
                        disabled={update.isPending}
                        className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
                      >
                        {update.isPending ? "Saving…" : "Save"}
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100"
                      >
                        Cancel
                      </button>
                      {update.isError && <span className="text-xs text-rose-600">Couldn’t save.</span>}
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={b.id}>
                  <td className="px-4 py-2 font-medium text-slate-900">{b.name}</td>
                  <td className="px-4 py-2">{b.domain}</td>
                  <td className="px-4 py-2">{b.geo}</td>
                  <td className="px-4 py-2">{b.goal}</td>
                  <td className="px-4 py-2 text-right">
                    <button onClick={() => startEdit(b)} className="text-sm font-medium text-indigo-600 hover:text-indigo-700">
                      Edit
                    </button>
                    <button onClick={() => setDeleting(b)} className="ml-3 text-sm font-medium text-rose-600 hover:text-rose-700">
                      Delete
                    </button>
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </Card>

      {/* delete confirmation */}
      {deleting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={() => setDeleting(null)}>
          <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-bold text-slate-900">Delete “{deleting.name}”?</h3>
            <p className="mt-2 text-sm text-slate-600">
              This permanently removes the business <span className="font-semibold">and all of its data</span> — audits,
              answers, gaps, plans, work-orders, content, mentions, reports. This cannot be undone.
            </p>
            <div className="mt-4 flex items-center justify-end gap-2">
              <button onClick={() => setDeleting(null)} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100">
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={del.isPending}
                className="rounded-md bg-rose-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50"
              >
                {del.isPending ? "Deleting…" : "Delete permanently"}
              </button>
            </div>
            {del.isError && <p className="mt-2 text-right text-xs text-rose-600">Couldn’t delete — try again.</p>}
          </div>
        </div>
      )}
    </div>
  );
}
