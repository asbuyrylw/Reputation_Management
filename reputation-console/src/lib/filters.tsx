"use client";

// Console-wide VIEW filters (distinct from tenant selection): which AI model to look
// through, and which time window. Pages/components opt in by reading useFilters(); a
// view that has nothing to filter simply ignores them.

import { createContext, useContext, useMemo, useState } from "react";

export type Period = "all" | "90d" | "30d";

interface FilterState {
  engine: string | null; // null = all models
  setEngine: (e: string | null) => void;
  period: Period;
  setPeriod: (p: Period) => void;
}

const FilterCtx = createContext<FilterState | null>(null);

export function FilterProvider({ children }: { children: React.ReactNode }) {
  const [engine, setEngine] = useState<string | null>(null);
  const [period, setPeriod] = useState<Period>("all");
  const value = useMemo(() => ({ engine, setEngine, period, setPeriod }), [engine, period]);
  return <FilterCtx.Provider value={value}>{children}</FilterCtx.Provider>;
}

export function useFilters(): FilterState {
  const c = useContext(FilterCtx);
  if (!c) throw new Error("useFilters must be used within <FilterProvider>");
  return c;
}

// How many days a period covers (null = unbounded). Used to filter dated series.
export function periodDays(p: Period): number | null {
  return p === "30d" ? 30 : p === "90d" ? 90 : null;
}

// Is an ISO date within the selected window (from "now")? Unbounded periods always pass.
export function withinPeriod(dateStr: string, p: Period): boolean {
  const days = periodDays(p);
  if (days == null) return true;
  const t = new Date(dateStr).getTime();
  if (Number.isNaN(t)) return true;
  return t >= Date.now() - days * 86400000;
}
