// Generic, readable renderer for the engine's flexible JSONB documents (gap model,
// site-audit summary). Scalars -> "Label: value"; arrays -> bulleted lists; nested
// objects -> indented sub-sections. Handles unknown shapes gracefully.

function humanize(k: string): string {
  return k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function renderInline(item: unknown): string {
  if (item && typeof item === "object" && !Array.isArray(item)) {
    return Object.entries(item as Record<string, unknown>)
      .map(([k, v]) => `${humanize(k)}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
      .join(" · ");
  }
  return String(item);
}

function Value({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    if (value.length === 0) return <p className="text-sm text-gray-400">—</p>;
    return (
      <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-gray-700">
        {value.map((item, i) => (
          <li key={i}>{renderInline(item)}</li>
        ))}
      </ul>
    );
  }
  if (value && typeof value === "object") {
    return (
      <div className="mt-1 space-y-3 border-l-2 border-gray-100 pl-3">
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <Block key={k} label={k} value={v} />
        ))}
      </div>
    );
  }
  return <p className="mt-0.5 text-sm text-gray-700">{String(value)}</p>;
}

function Block({ label, value }: { label: string; value: unknown }) {
  if (value == null || value === "") return null;
  return (
    <div>
      <div className="text-sm font-semibold text-gray-800">{humanize(label)}</div>
      <Value value={value} />
    </div>
  );
}

export function DataBlocks({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) return <p className="text-sm text-gray-400">No data.</p>;
  return (
    <div className="space-y-4">
      {entries.map(([k, v]) => (
        <Block key={k} label={k} value={v} />
      ))}
    </div>
  );
}
