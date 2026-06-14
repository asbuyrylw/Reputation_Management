"use client";

import { useState } from "react";
import { useBusiness } from "@/lib/business";
import { useCreateBusiness } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";

const FIELDS: [string, string][] = [
  ["name", "Name"],
  ["domain", "Domain"],
  ["goal", "Goal"],
  ["contested_terms", "Contested terms (comma-separated)"],
  ["geo", "Geo"],
  ["services", "Services"],
];
const EMPTY: Record<string, string> = { name: "", domain: "", goal: "", contested_terms: "", geo: "", services: "" };

export default function AdminBusinessesPage() {
  const { businesses, loading } = useBusiness();
  const create = useCreateBusiness();
  const [form, setForm] = useState<Record<string, string>>(EMPTY);

  if (loading) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Businesses"
        subtitle="The businesses the engine tracks. Create one, then run its first audit from Run jobs."
      />
      <Card className="mb-4">
        <div className="mb-2 text-sm font-medium text-gray-700">Add business</div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {FIELDS.map(([k, label]) => (
            <input
              key={k}
              placeholder={label}
              value={form[k]}
              onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
            />
          ))}
        </div>
        <button
          disabled={create.isPending || !form.name}
          onClick={() => create.mutate(form as { name: string }, { onSuccess: () => setForm(EMPTY) })}
          className="mt-3 rounded-md bg-gray-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          Create
        </button>
        {create.isError && <p className="mt-2 text-xs text-amber-700">Could not create the business.</p>}
      </Card>

      <Card className="overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">Domain</th>
              <th className="px-4 py-2">Geo</th>
              <th className="px-4 py-2">Goal</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {businesses.map((b) => (
              <tr key={b.id}>
                <td className="px-4 py-2">{b.name}</td>
                <td className="px-4 py-2">{b.domain}</td>
                <td className="px-4 py-2">{b.geo}</td>
                <td className="px-4 py-2">{b.goal}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
