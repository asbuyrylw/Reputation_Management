"use client";

// Selected-business context. Admins switch across all businesses; clients are
// pinned to their first accessible business (no switcher). The selected id keys
// every per-tenant query so switching never bleeds one business's data into another.

import { createContext, useContext, useEffect, useMemo, useState } from "react";
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

  const [businessId, setBusinessId] = useState<number | null>(null);

  // Default selection: first accessible business once the list loads.
  useEffect(() => {
    if (businessId == null && businesses.length > 0) {
      setBusinessId(businesses[0].id);
    }
  }, [businesses, businessId]);

  const canEdit = !!businesses.find((b) => b.id === businessId)?.can_edit;

  const value = useMemo<BusinessState>(
    () => ({ businesses, businessId, setBusinessId, isAdmin: !!isAdmin, canEdit, loading: isLoading }),
    [businesses, businessId, isAdmin, canEdit, isLoading],
  );

  return <BusinessCtx.Provider value={value}>{children}</BusinessCtx.Provider>;
}

export function useBusiness(): BusinessState {
  const c = useContext(BusinessCtx);
  if (!c) throw new Error("useBusiness must be used within <BusinessProvider>");
  return c;
}
