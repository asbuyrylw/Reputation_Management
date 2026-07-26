"use client";

// Content calendar — a month view of what's scheduled and when, from each task's due date. Plan
// and see your content + work across the month; click an item to open it on the task board.

import { useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useWorkOrders } from "@/lib/hooks";
import { PageHeader, Spinner, Card } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import type { WorkOrder } from "@/lib/types";
import { CONTENT_CAPS } from "@/lib/content";   // single shared producible-content set (see content.ts)

const isContent = (w: WorkOrder) => CONTENT_CAPS.has(w.capability ?? "");
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// local YYYY-MM-DD (avoid UTC drift from toISOString)
function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function statusTone(status: string, content: boolean): string {
  if (status === "done" || status === "verified") return "bg-emerald-100 text-emerald-700";
  if (status === "blocked") return "bg-rose-100 text-rose-700";
  return content ? "bg-indigo-100 text-indigo-700" : "bg-slate-100 text-slate-600";
}

export default function CalendarPage() {
  const { businessId } = useBusiness();
  const { data: workOrders, isLoading } = useWorkOrders(businessId);
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth()); // 0-11
  const [contentOnly, setContentOnly] = useState(false);

  if (isLoading) return <Spinner />;

  const all = (workOrders ?? []).filter((w) => !w.superseded && w.target_date);
  const scoped = contentOnly ? all.filter(isContent) : all;
  // bucket by due date (YYYY-MM-DD)
  const byDay = new Map<string, WorkOrder[]>();
  for (const w of scoped) {
    const key = (w.target_date || "").slice(0, 10);
    if (!key) continue;
    (byDay.get(key) ?? byDay.set(key, []).get(key)!).push(w);
  }

  // build the month grid (leading blanks + days)
  const first = new Date(year, month, 1);
  const startDow = first.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: (Date | null)[] = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d));
  while (cells.length % 7 !== 0) cells.push(null);

  const prevMonth = () => { if (month === 0) { setMonth(11); setYear((y) => y - 1); } else setMonth((m) => m - 1); };
  const nextMonth = () => { if (month === 11) { setMonth(0); setYear((y) => y + 1); } else setMonth((m) => m + 1); };
  const goToday = () => { setYear(today.getFullYear()); setMonth(today.getMonth()); };
  const monthCount = scoped.filter((w) => (w.target_date || "").slice(0, 7) === `${year}-${String(month + 1).padStart(2, "0")}`).length;

  return (
    <div>
      <PageHeader title="Content calendar" subtitle="What's scheduled and when — every task and content piece on its due date. Plan the month at a glance." />

      {all.length === 0 ? (
        <EmptyState title="Nothing scheduled yet" why="The calendar fills from your tasks' due dates." produces="Set due dates on your tasks (assign / dates), and they'll appear here on the month grid." cta={{ label: "Go to your tasks", href: "/content/work-orders" }} />
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <button onClick={prevMonth} className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-sm text-slate-600 hover:bg-slate-50">←</button>
              <span className="min-w-[150px] text-center text-sm font-bold text-slate-800">{MONTHS[month]} {year}</span>
              <button onClick={nextMonth} className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-sm text-slate-600 hover:bg-slate-50">→</button>
              <button onClick={goToday} className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50">Today</button>
            </div>
            <div className="flex items-center gap-3 text-xs text-slate-500">
              <label className="inline-flex items-center gap-1.5"><input type="checkbox" checked={contentOnly} onChange={(e) => setContentOnly(e.target.checked)} className="h-3.5 w-3.5 rounded border-slate-300" /> Content only</label>
              <span>{monthCount} this month</span>
            </div>
          </div>

          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
            <div className="grid grid-cols-7 border-b border-slate-200 bg-slate-50 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              {DOW.map((d) => <div key={d} className="px-2 py-1.5 text-center">{d}</div>)}
            </div>
            <div className="grid grid-cols-7">
              {cells.map((date, i) => {
                const key = date ? ymd(date) : "";
                const items = date ? (byDay.get(key) ?? []) : [];
                const isToday = date && key === ymd(today);
                return (
                  <div key={i} className={`min-h-[104px] border-b border-r border-slate-100 p-1.5 ${date ? "" : "bg-slate-50/50"}`}>
                    {date && (
                      <>
                        <div className={`mb-1 text-right text-[11px] ${isToday ? "font-bold text-indigo-600" : "text-slate-400"}`}>{date.getDate()}</div>
                        <div className="space-y-1">
                          {items.slice(0, 4).map((w) => (
                            <Link key={w.id} href={`/content/work-orders#wo-${w.id}`} title={w.title ?? ""}
                              className={`block truncate rounded px-1.5 py-0.5 text-[10.5px] font-medium ${statusTone(w.status, isContent(w))} hover:brightness-95`}>
                              {isContent(w) ? "✍️ " : ""}{w.title}
                            </Link>
                          ))}
                          {items.length > 4 && <div className="px-1 text-[10px] text-slate-400">+{items.length - 4} more</div>}
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
          <Card className="mt-3 bg-slate-50 text-[12px] text-slate-500">✍️ = content piece · indigo = content, grey = other task, green = done, red = blocked. Click any item to open it on the task board.</Card>
        </>
      )}
    </div>
  );
}
