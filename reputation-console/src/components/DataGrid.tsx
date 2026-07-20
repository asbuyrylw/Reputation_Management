"use client";

// A real data grid: everything visible in columns/rows (no click-to-expand to READ), with
// user-draggable column widths, a show/hide-columns menu, click-to-sort headers, optional
// select checkboxes for bulk actions, and an optional row click (e.g. to open an editor).
// Column widths + hidden columns persist per `storageKey`. Used by the drafts + strategy tables.

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

export type DataGridColumn<T> = {
  key: string;
  label: string;
  width?: number;            // initial px width
  minWidth?: number;         // min px when resizing (default 60)
  align?: "left" | "right" | "center";
  hideable?: boolean;        // default true; false = always shown (e.g. Title)
  defaultHidden?: boolean;   // starts hidden (user can show it)
  wrap?: boolean;            // true = cell wraps (multi-line lists) instead of truncating to one line
  sortValue?: (row: T) => string | number | null | undefined;  // enables sorting on this column
  render: (row: T) => ReactNode;
};

type Persist = { widths: Record<string, number>; hidden: string[] };

function loadPersist(key?: string): Persist | null {
  if (!key || typeof window === "undefined") return null;
  try { return JSON.parse(localStorage.getItem(`datagrid:${key}`) || "null"); } catch { return null; }
}
function savePersist(key: string | undefined, p: Persist) {
  if (!key || typeof window === "undefined") return;
  try { localStorage.setItem(`datagrid:${key}`, JSON.stringify(p)); } catch { /* ignore quota */ }
}

export function DataGrid<T>({
  columns, rows, getId, storageKey, onRowClick,
  selectable, selected, onToggle, onToggleAll, emptyText = "Nothing here.",
}: {
  columns: DataGridColumn<T>[];
  rows: T[];
  getId: (row: T) => number | string;
  storageKey?: string;
  onRowClick?: (row: T) => void;
  selectable?: boolean;
  selected?: Set<number | string>;
  onToggle?: (id: number | string) => void;
  onToggleAll?: (all: boolean) => void;
  emptyText?: string;
}) {
  const persisted = useRef<Persist | null>(loadPersist(storageKey));
  const [widths, setWidths] = useState<Record<string, number>>(() => {
    const w: Record<string, number> = {};
    for (const c of columns) w[c.key] = persisted.current?.widths?.[c.key] ?? c.width ?? 140;
    return w;
  });
  const [hidden, setHidden] = useState<Set<string>>(() =>
    new Set(persisted.current?.hidden ?? columns.filter((c) => c.defaultHidden).map((c) => c.key)));
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => { savePersist(storageKey, { widths, hidden: [...hidden] }); }, [widths, hidden, storageKey]);

  const visible = columns.filter((c) => !hidden.has(c.key));

  // --- column resize (drag the handle on a header's right edge) ---
  const drag = useRef<{ key: string; startX: number; startW: number } | null>(null);
  const onMouseMove = useCallback((e: MouseEvent) => {
    const d = drag.current;
    if (!d) return;
    const col = columns.find((c) => c.key === d.key);
    const next = Math.max(col?.minWidth ?? 60, d.startW + (e.clientX - d.startX));
    setWidths((w) => ({ ...w, [d.key]: next }));
  }, [columns]);
  const stopDrag = useCallback(() => {
    drag.current = null;
    document.removeEventListener("mousemove", onMouseMove);
    document.removeEventListener("mouseup", stopDrag);
    document.body.style.userSelect = "";
  }, [onMouseMove]);
  const startDrag = (e: React.MouseEvent, key: string) => {
    e.preventDefault(); e.stopPropagation();
    drag.current = { key, startX: e.clientX, startW: widths[key] };
    document.body.style.userSelect = "none";
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", stopDrag);
  };

  // --- sorting ---
  const sorted = (() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    return [...rows].sort((a, b) => {
      const va = col.sortValue!(a), vb = col.sortValue!(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1; if (vb == null) return -1;
      if (va < vb) return -1 * sort.dir;
      if (va > vb) return 1 * sort.dir;
      return 0;
    });
  })();
  const toggleSort = (c: DataGridColumn<T>) => {
    if (!c.sortValue) return;
    setSort((s) => s?.key === c.key ? (s.dir === 1 ? { key: c.key, dir: -1 } : null) : { key: c.key, dir: 1 });
  };

  const allSelected = selectable && rows.length > 0 && rows.every((r) => selected?.has(getId(r)));

  return (
    <div>
      {/* columns menu */}
      <div className="mb-2 flex items-center justify-end">
        <div className="relative">
          <button type="button" onClick={() => setMenuOpen((o) => !o)}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50">
            Columns ▾
          </button>
          {menuOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
              <div className="absolute right-0 z-20 mt-1 w-52 rounded-lg border border-slate-200 bg-white p-1.5 shadow-lg">
                {columns.filter((c) => c.hideable !== false).map((c) => (
                  <label key={c.key} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-xs text-slate-700 hover:bg-slate-50">
                    <input type="checkbox" checked={!hidden.has(c.key)} onChange={() => setHidden((h) => { const n = new Set(h); if (n.has(c.key)) n.delete(c.key); else n.add(c.key); return n; })} className="h-3.5 w-3.5 rounded border-slate-300" />
                    {c.label}
                  </label>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="text-left text-sm" style={{ tableLayout: "fixed", width: "max-content", minWidth: "100%" }}>
          <colgroup>
            {selectable && <col style={{ width: 36 }} />}
            {visible.map((c) => <col key={c.key} style={{ width: widths[c.key] }} />)}
          </colgroup>
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-400">
              {selectable && (
                <th className="py-2 pl-3">
                  <input type="checkbox" checked={!!allSelected} onChange={(e) => onToggleAll?.(e.target.checked)} className="h-3.5 w-3.5 rounded border-slate-300" aria-label="Select all" />
                </th>
              )}
              {visible.map((c) => (
                <th key={c.key} className={`relative py-2 pr-3 ${c.align === "right" ? "text-right" : c.align === "center" ? "text-center" : "text-left"} ${c.sortValue ? "cursor-pointer select-none" : ""}`} onClick={() => toggleSort(c)}>
                  <span className="pl-3">{c.label}{sort?.key === c.key && <span className="ml-0.5 text-indigo-500">{sort.dir === 1 ? "↑" : "↓"}</span>}</span>
                  {/* resize handle */}
                  <span onMouseDown={(e) => startDrag(e, c.key)} onClick={(e) => e.stopPropagation()}
                    className="absolute right-0 top-0 h-full w-1.5 cursor-col-resize hover:bg-indigo-300" title="Drag to resize" />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr><td colSpan={visible.length + (selectable ? 1 : 0)} className="px-3 py-6 text-center text-sm text-slate-400">{emptyText}</td></tr>
            ) : sorted.map((r) => {
              const id = getId(r);
              return (
                <tr key={id} className={`border-b border-slate-100 last:border-0 hover:bg-slate-50 ${onRowClick ? "cursor-pointer" : ""}`} onClick={() => onRowClick?.(r)}>
                  {selectable && (
                    <td className="py-2 pl-3" onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" checked={!!selected?.has(id)} onChange={() => onToggle?.(id)} className="h-3.5 w-3.5 rounded border-slate-300" aria-label="Select row" />
                    </td>
                  )}
                  {visible.map((c) => (
                    <td key={c.key} className={`py-2 pr-3 pl-3 align-top ${c.wrap ? "" : "overflow-hidden"} ${c.align === "right" ? "text-right" : c.align === "center" ? "text-center" : ""}`}>
                      <div className={c.wrap ? "whitespace-normal break-words" : "truncate"}>{c.render(r)}</div>
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
