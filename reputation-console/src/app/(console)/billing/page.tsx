"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { useBillingPlans, useSubscription, useCheckout, useBillingPortal } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import type { BillingPlan } from "@/lib/types";

const money = (n: number) => `$${n.toLocaleString()}`;
const cap = (v: number | null, unit: string) => (v == null ? "Unlimited" : `${v} ${unit}`);

function PlanCard({ plan, current, canManage, onChoose, busy }: {
  plan: BillingPlan; current: boolean; canManage: boolean; onChoose: () => void; busy: boolean;
}) {
  return (
    <Card className={current ? "ring-2 ring-indigo-500" : ""}>
      <div className="flex items-baseline justify-between">
        <h3 className="text-base font-bold text-slate-900">{plan.name}</h3>
        {current && <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[11px] font-semibold text-indigo-700">Current</span>}
      </div>
      <div className="mt-1 text-2xl font-bold text-slate-900">{money(plan.price_usd_month)}<span className="text-sm font-medium text-slate-400">/mo</span></div>
      <ul className="mt-3 space-y-1 text-xs text-slate-600">
        <li>{cap(plan.max_businesses, "businesses")}</li>
        <li>{cap(plan.max_audits_per_month, "audits / month")}</li>
        <li>{cap(plan.max_engines, "AI engines")}</li>
        <li>{cap(plan.seats, "seats")}</li>
        {plan.trial_days ? <li className="text-emerald-700">{plan.trial_days}-day free trial</li> : null}
      </ul>
      {canManage && !current && (
        <button
          onClick={onChoose}
          disabled={busy}
          className="mt-4 w-full rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {busy ? "Redirecting…" : "Choose plan"}
        </button>
      )}
    </Card>
  );
}

export default function BillingPage() {
  const { user } = useAuth();
  const plans = useBillingPlans();
  const sub = useSubscription();
  const checkout = useCheckout();
  const portal = useBillingPortal();

  const canManage = user?.role === "admin" || user?.org_role === "owner" || user?.org_role === "admin";
  const currentCode = sub.data?.subscription?.plan_code ?? null;

  const goCheckout = (plan_code: string) =>
    checkout.mutate({ plan_code }, { onSuccess: (r) => { if (r?.url) window.location.href = r.url; } });
  const goPortal = () =>
    portal.mutate(undefined, { onSuccess: (r) => { if (r?.url) window.location.href = r.url; } });

  // The whole billing system is built but stays dormant until the platform owner turns it on.
  if (!user?.billing_enabled) {
    return (
      <div>
        <PageHeader eyebrow="Settings" title="Billing & plans" subtitle="Subscription, usage, and payment for your organization." />
        <Card className="border-indigo-100 bg-indigo-50/40">
          <h3 className="text-sm font-semibold text-slate-900">Billing isn’t enabled yet</h3>
          <p className="mt-1 text-sm text-slate-600">
            Your account isn’t being billed. Everything you see is included while we’re in pilot.
          </p>
          {user?.is_super_admin && (
            <p className="mt-2 text-xs text-slate-500">
              You’re the platform owner — flip the master switch under{" "}
              <Link href="/account" className="font-medium text-indigo-600 hover:text-indigo-700">Account → Platform</Link> to turn billing on.
            </p>
          )}
        </Card>
      </div>
    );
  }

  if (plans.isLoading) return <Spinner />;

  const summary = sub.data;
  return (
    <div>
      <PageHeader eyebrow="Settings" title="Billing & plans" subtitle="Your subscription, this month’s usage, and payment." />

      {summary && (
        <Card className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-900">
                {summary.plan ? summary.plan.name : "No plan"} · <span className={summary.active ? "text-emerald-700" : "text-rose-600"}>{summary.subscription?.status ?? "none"}</span>
              </div>
              <div className="mt-0.5 text-xs text-slate-500">
                {summary.usage.audits_this_month} audit{summary.usage.audits_this_month === 1 ? "" : "s"} this month ·{" "}
                {summary.usage.businesses} business{summary.usage.businesses === 1 ? "" : "es"}
                {summary.plan?.max_audits_per_month != null && ` · limit ${summary.plan.max_audits_per_month}/mo`}
              </div>
            </div>
            {canManage && currentCode && (
              <button
                onClick={goPortal}
                disabled={portal.isPending}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
              >
                {portal.isPending ? "Opening…" : "Manage billing"}
              </button>
            )}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {(plans.data ?? []).map((p) => (
          <PlanCard
            key={p.code}
            plan={p}
            current={p.code === currentCode}
            canManage={!!canManage}
            onChoose={() => goCheckout(p.code)}
            busy={checkout.isPending}
          />
        ))}
      </div>

      {!canManage && (
        <p className="mt-4 text-xs text-slate-400">Only an organization owner or admin can change the plan.</p>
      )}
      {checkout.isError && <p className="mt-3 text-xs text-rose-600">Couldn’t start checkout — billing may not be fully configured yet.</p>}
    </div>
  );
}
