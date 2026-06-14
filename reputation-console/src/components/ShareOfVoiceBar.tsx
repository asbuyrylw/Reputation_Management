// Stacked owned/neutral/contested citation share. Owned=navy, neutral=gray,
// contested=rust — the report's palette, kept consistent across the console.

const ORDER = [
  { key: "owned", color: "#1F3A5F", label: "Owned" },
  { key: "neutral", color: "#9CA3AF", label: "Neutral" },
  { key: "contested", color: "#8A3B2E", label: "Contested" },
];

export function ShareOfVoiceBar({ byClass }: { byClass: Record<string, { cites: number; share: number }> }) {
  const total = Object.values(byClass).reduce((a, v) => a + (v?.cites || 0), 0) || 1;
  return (
    <div>
      <div className="flex h-4 w-full overflow-hidden rounded">
        {ORDER.map((o) => {
          const c = byClass[o.key]?.cites || 0;
          const w = (c / total) * 100;
          return w > 0 ? <div key={o.key} style={{ width: `${w}%`, background: o.color }} title={`${o.label}: ${c}`} /> : null;
        })}
      </div>
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-gray-600">
        {ORDER.map((o) => {
          const c = byClass[o.key]?.cites || 0;
          return (
            <span key={o.key} className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-3 rounded" style={{ background: o.color }} />
              {o.label} {Math.round((c / total) * 100)}%
            </span>
          );
        })}
      </div>
    </div>
  );
}
