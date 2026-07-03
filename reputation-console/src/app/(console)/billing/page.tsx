"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { useBillingPlans, useSubscription, useCheckout, useBillingPortal } from "@/lib/hooks";
import { Button, Card, Chip, PageHeader, Spinner } from "@/components/ui";
import type { BillingPlan } from "@/lib/types";

const money = (n: number) => `$${n.toLocaleString()}`;
const cap = (v: number | null, unit: string) => (v == null ? "Unlimited" : `${v} ${unit}`);

function PlanCard({ plan, current, canManage, onChoose, busy }: {
  plan: BillingPlan; current: boolean; canManage: boolean; onChoose: () => void; busy: boolean;
}) {
  return (
    <Card className={current ? "ring-2 ring-indigo-500" : ""}>
      <div className="flex items-baseline justify-between">
        <h3 className="text-base font-bold text-ink">{plan.name}</h3>
        {current && <Chip tone="info">Current</Chip>}
      </div>
      <div className="mt-1 text-2xl font-bold text-ink">{money(plan.price_usd_month)}<span className="text-sm font-medium text-ink-4">/mo</span></div>
      <ul className="mt-3 space-y-1 text-xs text-ink-3">
        <li>{cap(plan.max_businesses, "businesses")}</li>
        <li>{cap(plan.max_audits_per_month, "audits / month")}</li>
        <li>{cap(plan.max_engines, "AI engines")}</li>
        <li>{cap(plan.seats, "seats")}</li>
        {plan.trial_days ? <li className="text-good">{plan.trial_days}-day free trial</li> : null}
      </ul>
      {canManage && !current && (
        <Button
          variant="primary"
          onClick={onChoose}
          disabled={busy}
          className="mt-4 w-full"
        >
          {busy ? "Redirecting…" : "Choose plan"}
        </Button>
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
          <h3 className="text-sm font-semibold text-ink">Billing isn’t enabled yet</h3>
          <p className="mt-1 text-sm text-ink-3">
            Your account isn’t being billed. Everything you see is included while we’re in pilot.
          </p>
          {user?.is_super_admin && (
            <p className="mt-2 text-xs text-ink-3">
              You’re the platform owner — flip the master switch under{" "}
              <Link href="/account" className="font-medium text-indigo hover:text-indigo-strong">Account → Platform</Link> to turn billing on.
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
              <div className="text-sm font-semibold text-ink">
                {summary.plan ? summary.plan.name : "No plan"} · <span className={summary.active ? "text-good" : "text-alert"}>{summary.subscription?.status ?? "none"}</span>
              </div>
              <div className="mt-0.5 text-xs text-ink-3">
                {summary.usage.audits_this_month} audit{summary.usage.audits_this_month === 1 ? "" : "s"} this month ·{" "}
                {summary.usage.businesses} business{summary.usage.businesses === 1 ? "" : "es"}
                {summary.plan?.max_audits_per_month != null && ` · limit ${summary.plan.max_audits_per_month}/mo`}
              </div>
            </div>
            {canManage && currentCode && (
              <Button
                variant="secondary"
                onClick={goPortal}
                disabled={portal.isPending}
              >
                {portal.isPending ? "Opening…" : "Manage billing"}
              </Button>
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
        <p className="mt-4 text-xs text-ink-4">Only an organization owner or admin can change the plan.</p>
      )}
      {checkout.isError && <p className="mt-3 text-xs text-alert">Couldn’t start checkout — billing may not be fully configured yet.</p>}
    </div>
  );
}
