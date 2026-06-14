"use client";

import { useBusiness } from "@/lib/business";

export function BusinessSwitcher() {
  const { businesses, businessId, setBusinessId, isAdmin } = useBusiness();
  const current = businesses.find((b) => b.id === businessId);

  // Clients are pinned to their business -- no switcher, just the name.
  if (!isAdmin) {
    return <span className="text-sm font-medium text-gray-900">{current?.name ?? "—"}</span>;
  }
  return (
    <select
      value={businessId ?? ""}
      onChange={(e) => setBusinessId(Number(e.target.value))}
      className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-900"
      aria-label="Select business"
    >
      {businesses.map((b) => (
        <option key={b.id} value={b.id}>
          {b.name}
        </option>
      ))}
    </select>
  );
}
