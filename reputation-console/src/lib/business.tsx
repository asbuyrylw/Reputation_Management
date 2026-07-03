"use client";

// Selected-business context. Admins switch across all businesses; clients are
// pinned to their first accessible business (no switcher). The selected id keys
// every per-tenant query so switching never bleeds one business's data into another.

import { createContext, useContext, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";
import { useAuth } from "./auth";
import type { Business } from "./types";

interface BusinessState {
  businesses: Business[];
  businessId: number | null;
  setBusinessId: (id: number) => void;
  isAdmin: boolean;
  canEdit: boolean; // may the current user act on the selected business?
  loading: boolean;
}

const BusinessCtx = createContext<BusinessState | null>(null);

export function BusinessProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const { data: businesses = [], isLoading } = useQuery({
    queryKey: ["businesses"],
    queryFn: () => apiFetch<Business[]>("/businesses"),
    enabled: !!user,
  });

  // The user's explicit pick (null until they switch). The EFFECTIVE id is derived during
  // render — no store-then-correct effect — so there's no first-render flash of null, and it
  // self-heals to the first business if the selected one is deleted (otherwise the switcher
  // would point at a dead id and every query would 404).
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const businessId = useMemo(() => {
    if (selectedId != null && businesses.some((b) => b.id === selectedId)) return selectedId;
    return businesses[0]?.id ?? null;
  }, [selectedId, businesses]);
  const setBusinessId = setSelectedId;

  const canEdit = !!businesses.find((b) => b.id === businessId)?.can_edit;

  const value = useMemo<BusinessState>(
    () => ({ businesses, businessId, setBusinessId, isAdmin: !!isAdmin, canEdit, loading: isLoading }),
    [businesses, businessId, setBusinessId, isAdmin, canEdit, isLoading],
  );

  return <BusinessCtx.Provider value={value}>{children}</BusinessCtx.Provider>;
}

export function useBusiness(): BusinessState {
  const c = useContext(BusinessCtx);
  if (!c) throw new Error("useBusiness must be used within <BusinessProvider>");
  return c;
}
