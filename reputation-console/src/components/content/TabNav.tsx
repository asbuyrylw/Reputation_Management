// A small in-page segmented tab bar for filtering lists (drafts by status, approvals by surface).
// Active tab = solid ink; inactive = neutral chip. Not the hub-level HubTabs — this is a local
// filter control. Each tab may carry an optional count.

export type TabItem = { key: string; label: string; count?: number };

export function TabNav({
  tabs,
  active,
  onSelect,
  className = "",
}: {
  tabs: TabItem[];
  active: string;
  onSelect: (key: string) => void;
  className?: string;
}) {
  return (
    <div className={`flex flex-wrap gap-1.5 ${className}`}>
      {tabs.map((t) => {
        const on = t.key === active;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onSelect(t.key)}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[13px] font-semibold transition ${
              on ? "bg-ink text-white" : "bg-paper text-ink-3 ring-1 ring-inset ring-line-2 hover:bg-line/60"
            }`}
          >
            {t.label}
            {t.count != null && (
              <span className={`rounded-full px-1.5 text-[11px] font-mono ${on ? "bg-white/20 text-white" : "bg-line text-ink-4"}`}>{t.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
