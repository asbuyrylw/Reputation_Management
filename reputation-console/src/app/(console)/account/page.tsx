"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useBusiness } from "@/lib/business";
import {
  useRevokeSessions,
  useDeleteBusiness,
  usePlatformSettings,
  useSetBillingEnabled,
  useIntegrationSettings,
  useUpdateIntegrationSettings,
} from "@/lib/hooks";
import { apiDownload, ApiError } from "@/lib/api";
import { Card, PageHeader } from "@/components/ui";
import type { IntegrationSettings } from "@/lib/types";

// Platform owner (super-admin) only: the billing master switch. The whole billing system is
// wired but dormant until this is flipped on.
function PlatformCard() {
  const { refresh } = useAuth();
  const settings = usePlatformSettings();
  const setBilling = useSetBillingEnabled();
  const enabled = settings.data?.billing_enabled ?? false;
  const toggle = (on: boolean) =>
    setBilling.mutate(on, { onSuccess: () => refresh() });
  return (
    <Card className="border-amber-200 bg-amber-50/40">
      <h3 className="text-sm font-semibold text-slate-900">Platform — billing master switch</h3>
      <p className="mt-1 text-sm text-slate-600">
        Turn the billing system on or off for the whole platform. While off, no one is metered or charged and the
        billing UI is hidden. The pilot organization stays exempt even when this is on.
      </p>
      <div className="mt-3 flex items-center gap-3">
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${enabled ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-600"}`}>
          {settings.isLoading ? "…" : enabled ? "Billing is ON" : "Billing is OFF"}
        </span>
        {enabled ? (
          <button
            onClick={() => toggle(false)}
            disabled={setBilling.isPending}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
          >
            {setBilling.isPending ? "…" : "Turn billing off"}
          </button>
        ) : (
          <button
            onClick={() => toggle(true)}
            disabled={setBilling.isPending}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {setBilling.isPending ? "…" : "Turn billing on"}
          </button>
        )}
      </div>
      {setBilling.isError && <p className="mt-2 text-xs text-rose-600">Couldn’t change the setting — try again.</p>}
    </Card>
  );
}

// A labeled toggle row. Auto-post toggles are disabled (with a lock hint) unless the user
// is an org manager; other toggles (notifications, require-approval) are always editable.
function ToggleRow({
  label,
  hint,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className={`flex items-start justify-between gap-3 py-2 ${disabled ? "opacity-60" : ""}`}>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-slate-800">{label}</span>
        {hint && <span className="block text-xs text-slate-500">{hint}</span>}
      </span>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 shrink-0 disabled:cursor-not-allowed"
      />
    </label>
  );
}

// Per-business automation settings. The owner controls approval + notifications; auto-post
// fields are org-manager-gated, and the platform kill-switch state is shown read-only.
function AutomationCard({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const { data, isLoading } = useIntegrationSettings(businessId);
  const update = useUpdateIntegrationSettings(businessId);
  const [err, setErr] = useState<string | null>(null);

  if (isLoading || !data) return null;
  const s = data.settings;
  const canManageAuto = data.can_manage_autopost && canEdit;
  const globallyOn = data.autopost_globally_enabled;

  const save = (patch: Partial<IntegrationSettings>) => {
    setErr(null);
    update.mutate(patch, {
      onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't save — try again."),
    });
  };

  // Auto-post is only truly active when the platform switch is on AND the business allows it.
  const autoEffective = globallyOn && s.allow_owned_autopost;

  return (
    <Card>
      <h3 className="text-sm font-semibold text-slate-900">Automation</h3>
      <p className="mt-1 text-sm text-slate-600">
        Control what posts on its own versus what waits for your approval. Approving keeps you in the loop;
        automation moves faster once you trust it.
      </p>

      {/* platform kill-switch (read-only) */}
      <div className={`mt-3 rounded-lg px-3 py-2 text-xs ${globallyOn ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
        {globallyOn
          ? "Automated posting is enabled platform-wide."
          : "Automated posting is currently OFF platform-wide — auto-post settings are saved but won't post until it's turned on."}
      </div>

      <div className="mt-2 divide-y divide-slate-100">
        <ToggleRow
          label="Require approval before anything is posted"
          hint="Everything lands in your approval inbox first."
          checked={s.require_approval}
          disabled={!canEdit}
          onChange={(v) => save({ require_approval: v })}
        />
        <ToggleRow
          label="Auto-publish to surfaces you own"
          hint={
            canManageAuto
              ? autoEffective
                ? "Approved content publishes to your site / Google profile automatically."
                : "Allowed for this business — activates when the platform switch is on."
              : "Org manager only."
          }
          checked={s.allow_owned_autopost}
          disabled={!canManageAuto}
          onChange={(v) => save({ allow_owned_autopost: v })}
        />
        <ToggleRow
          label="Auto-reply to reviews"
          hint={canManageAuto ? `Only ${s.auto_reply_min_stars}★ and up, screened for compliance.` : "Org manager only."}
          checked={s.auto_reply_reviews}
          disabled={!canManageAuto}
          onChange={(v) => save({ auto_reply_reviews: v })}
        />
        <ToggleRow
          label="Auto-reply to mentions"
          hint={canManageAuto ? "Drafts a reply and posts it on owned surfaces." : "Org manager only."}
          checked={s.auto_reply_mentions}
          disabled={!canManageAuto}
          onChange={(v) => save({ auto_reply_mentions: v })}
        />
        <ToggleRow
          label="Email me about items needing attention"
          checked={s.notify_email}
          disabled={!canEdit}
          onChange={(v) => save({ notify_email: v })}
        />
        <ToggleRow
          label="Email me when something posts automatically"
          checked={s.notify_on_auto}
          disabled={!canEdit}
          onChange={(v) => save({ notify_on_auto: v })}
        />
      </div>

      {!data.can_manage_autopost && (
        <p className="mt-2 text-xs text-slate-400">
          Auto-post settings are managed by an organization manager. You can still set approval and notification
          preferences.
        </p>
      )}
      {err && <p className="mt-2 text-xs text-rose-600">{err}</p>}
    </Card>
  );
}

export default function AccountPage() {
  const router = useRouter();
  const { user } = useAuth();
  const { businessId, businesses, canEdit } = useBusiness();
  const revoke = useRevokeSessions();
  const del = useDeleteBusiness(businessId);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState("");

  const biz = businesses.find((b) => b.id === businessId);
  const isAdmin = user?.role === "admin";

  const signOutEverywhere = () =>
    revoke.mutate(undefined, { onSuccess: () => router.replace("/login") });

  const exportData = async () => {
    setExporting(true);
    setExportError(null);
    try {
      const name = (biz?.name || "business").replace(/\s+/g, "_");
      await apiDownload(`/businesses/${businessId}/export`, `${name}_data_export.json`);
    } catch {
      setExportError("Export failed. Please try again.");
    } finally {
      setExporting(false);
    }
  };

  const deleteBusiness = () =>
    del.mutate(undefined, { onSuccess: () => router.replace("/dashboard") });

  return (
    <div className="max-w-2xl">
      <PageHeader title="Account & data" subtitle="Manage your sessions and your data." />

      <div className="space-y-4">
        {/* platform owner only: the billing master switch */}
        {user?.is_super_admin && <PlatformCard />}

        {/* per-business automation / auto-post settings */}
        <AutomationCard businessId={businessId} canEdit={canEdit} />

        {/* sessions */}
        <Card>
          <h3 className="text-sm font-semibold text-slate-900">Sessions</h3>
          <p className="mt-1 text-sm text-slate-600">
            Sign out of every device and browser. Anyone currently signed in (including you) will need to log in again.
          </p>
          <button
            onClick={signOutEverywhere}
            disabled={revoke.isPending}
            className="mt-3 rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            {revoke.isPending ? "Signing out…" : "Sign out everywhere"}
          </button>
          {revoke.isError && (
            <p className="mt-2 text-xs text-rose-600">Could not sign out everywhere — please try again.</p>
          )}
        </Card>

        {/* data export */}
        <Card>
          <h3 className="text-sm font-semibold text-slate-900">Export your data</h3>
          <p className="mt-1 text-sm text-slate-600">
            Download everything we hold for <span className="font-medium">{biz?.name ?? "this business"}</span> as a
            single JSON file (audits, prompts, content, mentions, and more).
          </p>
          <button
            onClick={exportData}
            disabled={exporting || !businessId}
            className="mt-3 rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            {exporting ? "Preparing…" : "Export business data"}
          </button>
          {exportError && <p className="mt-2 text-xs text-rose-600">{exportError}</p>}
        </Card>

        {/* danger zone (admin only) */}
        {isAdmin && (
          <Card className="border-rose-200">
            <h3 className="text-sm font-semibold text-rose-700">Delete this business</h3>
            <p className="mt-1 text-sm text-slate-600">
              Permanently erase <span className="font-medium">{biz?.name ?? "this business"}</span> and all of its
              data. This cannot be undone. Type the business name to confirm.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder={biz?.name ?? "business name"}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              />
              <button
                onClick={deleteBusiness}
                disabled={del.isPending || !biz || confirmText !== biz.name}
                className="rounded-md bg-rose-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50"
              >
                {del.isPending ? "Deleting…" : "Delete business"}
              </button>
            </div>
            {del.isError && <p className="mt-2 text-xs text-rose-600">{(del.error as Error)?.message}</p>}
          </Card>
        )}
      </div>
    </div>
  );
}
