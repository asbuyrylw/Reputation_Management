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
  useBranding,
  useSetBranding,
  useShareLink,
  useLeads,
} from "@/lib/hooks";
import { apiDownload, ApiError } from "@/lib/api";
import { Card, PageHeader, Button, Input, Chip } from "@/components/ui";
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
    <Card className="border-amber-bg bg-amber-bg/40">
      <h3 className="text-sm font-semibold text-ink">Platform — billing master switch</h3>
      <p className="mt-1 text-sm text-ink-3">
        Turn the billing system on or off for the whole platform. While off, no one is metered or charged and the
        billing UI is hidden. The pilot organization stays exempt even when this is on.
      </p>
      <div className="mt-3 flex items-center gap-3">
        <Chip tone={enabled ? "good" : "neutral"}>
          {settings.isLoading ? "…" : enabled ? "Billing is ON" : "Billing is OFF"}
        </Chip>
        {enabled ? (
          <Button
            variant="secondary"
            onClick={() => toggle(false)}
            disabled={setBilling.isPending}
          >
            {setBilling.isPending ? "…" : "Turn billing off"}
          </Button>
        ) : (
          <Button
            onClick={() => toggle(true)}
            disabled={setBilling.isPending}
          >
            {setBilling.isPending ? "…" : "Turn billing on"}
          </Button>
        )}
      </div>
      {setBilling.isError && <p className="mt-2 text-xs text-alert">Couldn’t change the setting — try again.</p>}
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
        <span className="block text-sm font-medium text-ink-2">{label}</span>
        {hint && <span className="block text-xs text-ink-3">{hint}</span>}
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
      <h3 className="text-sm font-semibold text-ink">Automation</h3>
      <p className="mt-1 text-sm text-ink-3">
        Control what posts on its own versus what waits for your approval. Approving keeps you in the loop;
        automation moves faster once you trust it.
      </p>

      {/* platform kill-switch (read-only) */}
      <div className={`mt-3 rounded-lg px-3 py-2 text-xs ${globallyOn ? "bg-good-bg text-good" : "bg-line text-ink-3"}`}>
        {globallyOn
          ? "Automated posting is enabled platform-wide."
          : "Automated posting is currently OFF platform-wide — auto-post settings are saved but won't post until it's turned on."}
      </div>

      <div className="mt-2 divide-y divide-line">
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
        <p className="mt-2 text-xs text-ink-4">
          Auto-post settings are managed by an organization manager. You can still set approval and notification
          preferences.
        </p>
      )}
      {err && <p className="mt-2 text-xs text-alert">{err}</p>}
    </Card>
  );
}

// White-label & sharing: agency branding for the public lead-magnet page, a shareable
// public audit link, and the emails captured from that page. Edits are canEdit-gated.
function WhiteLabelCard({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const { data: branding } = useBranding(businessId);
  const setBranding = useSetBranding(businessId);
  const shareLink = useShareLink(businessId);
  const { data: leadsData } = useLeads(businessId);

  // local form state, seeded from the loaded branding (only while not yet dirtied)
  const [brandName, setBrandName] = useState<string | null>(null);
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [accent, setAccent] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);

  const bName = brandName ?? branding?.brand_name ?? "";
  const bLogo = logoUrl ?? branding?.logo_url ?? "";
  const bAccent = accent ?? branding?.accent ?? "#4f46e5";

  const save = () => {
    setSaved(false);
    setBranding.mutate(
      { brand_name: bName, logo_url: bLogo, accent: bAccent },
      { onSuccess: () => setSaved(true) },
    );
  };

  const link = shareLink.data?.url ?? null;
  const copyLink = () => {
    if (!link) return;
    navigator.clipboard?.writeText(link).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      },
      () => {},
    );
  };

  const leads = leadsData?.leads ?? [];
  const sortedLeads = [...leads].sort(
    (a, b) => new Date(b.captured_at).getTime() - new Date(a.captured_at).getTime(),
  );

  return (
    <Card>
      <h3 className="text-sm font-semibold text-ink">White-label &amp; sharing</h3>
      <p className="mt-1 text-sm text-ink-3">
        Brand the public audit page with your own name, logo, and color, then share a lead-magnet link that
        captures emails from prospects who want their full reputation report.
      </p>

      {/* branding form */}
      <div className="mt-4 space-y-3">
        <div>
          <label className="block text-xs font-medium text-ink-2" htmlFor="wl-name">Brand name</label>
          <Input
            id="wl-name"
            value={bName}
            onChange={(e) => setBrandName(e.target.value)}
            disabled={!canEdit}
            placeholder="Your agency or business name"
            className="mt-1"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-ink-2" htmlFor="wl-logo">Logo URL</label>
          <Input
            id="wl-logo"
            value={bLogo}
            onChange={(e) => setLogoUrl(e.target.value)}
            disabled={!canEdit}
            placeholder="https://…/logo.png"
            className="mt-1"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-ink-2" htmlFor="wl-accent">Accent color</label>
          <div className="mt-1 flex items-center gap-2">
            <input
              id="wl-accent"
              type="color"
              value={/^#[0-9a-fA-F]{6}$/.test(bAccent) ? bAccent : "#4f46e5"}
              onChange={(e) => setAccent(e.target.value)}
              disabled={!canEdit}
              className="h-8 w-10 cursor-pointer rounded border border-line-2 disabled:cursor-not-allowed"
            />
            <Input
              value={bAccent}
              onChange={(e) => setAccent(e.target.value)}
              disabled={!canEdit}
              placeholder="#4f46e5"
              className="w-28"
            />
          </div>
        </div>
        {canEdit && (
          <div className="flex items-center gap-3">
            <Button
              onClick={save}
              disabled={setBranding.isPending}
            >
              {setBranding.isPending ? "Saving…" : "Save branding"}
            </Button>
            {saved && !setBranding.isPending && <span className="text-xs text-good">Saved.</span>}
            {setBranding.isError && <span className="text-xs text-alert">Couldn’t save — try again.</span>}
          </div>
        )}
      </div>

      {/* public share link */}
      <div className="mt-5 border-t border-line pt-4">
        <h4 className="text-sm font-semibold text-ink">Public audit link</h4>
        <p className="mt-1 text-xs text-ink-3">
          A shareable, branded lead-magnet page anyone can open (no login). It shows a teaser of this business’s
          AI reputation and captures the prospect’s email in exchange for the full report.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => shareLink.mutate()}
            disabled={shareLink.isPending || !businessId}
          >
            {shareLink.isPending ? "Generating…" : link ? "Regenerate link" : "Generate share link"}
          </Button>
          {link && (
            <>
              <input
                readOnly
                value={link}
                onFocus={(e) => e.currentTarget.select()}
                className="min-w-0 flex-1 rounded-md border border-line bg-paper px-3 py-1.5 text-sm text-ink-3"
              />
              <Button
                variant="secondary"
                onClick={copyLink}
              >
                {copied ? "Copied!" : "Copy"}
              </Button>
            </>
          )}
        </div>
        {shareLink.isError && <p className="mt-2 text-xs text-alert">Couldn’t generate a link — try again.</p>}
      </div>

      {/* captured leads */}
      <div className="mt-5 border-t border-line pt-4">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-ink">Captured leads</h4>
          <Chip tone="neutral">{sortedLeads.length}</Chip>
        </div>
        {sortedLeads.length === 0 ? (
          <p className="mt-2 text-xs text-ink-3">
            No leads yet. Share your public audit link to start capturing emails.
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-line">
            {sortedLeads.map((lead) => (
              <li key={lead.id} className="flex items-center justify-between gap-3 py-2">
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-ink-2">{lead.email}</span>
                  {lead.name && <span className="block truncate text-xs text-ink-3">{lead.name}</span>}
                </span>
                <span className="shrink-0 text-xs text-ink-4">
                  {new Date(lead.captured_at).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
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

        {/* white-label branding + public lead-magnet link + captured leads */}
        <WhiteLabelCard businessId={businessId} canEdit={canEdit} />

        {/* sessions */}
        <Card>
          <h3 className="text-sm font-semibold text-ink">Sessions</h3>
          <p className="mt-1 text-sm text-ink-3">
            Sign out of every device and browser. Anyone currently signed in (including you) will need to log in again.
          </p>
          <Button
            variant="secondary"
            onClick={signOutEverywhere}
            disabled={revoke.isPending}
            className="mt-3"
          >
            {revoke.isPending ? "Signing out…" : "Sign out everywhere"}
          </Button>
          {revoke.isError && (
            <p className="mt-2 text-xs text-alert">Could not sign out everywhere — please try again.</p>
          )}
        </Card>

        {/* data export */}
        <Card>
          <h3 className="text-sm font-semibold text-ink">Export your data</h3>
          <p className="mt-1 text-sm text-ink-3">
            Download everything we hold for <span className="font-medium">{biz?.name ?? "this business"}</span> as a
            single JSON file (audits, prompts, content, mentions, and more).
          </p>
          <Button
            variant="secondary"
            onClick={exportData}
            disabled={exporting || !businessId}
            className="mt-3"
          >
            {exporting ? "Preparing…" : "Export business data"}
          </Button>
          {exportError && <p className="mt-2 text-xs text-alert">{exportError}</p>}
        </Card>

        {/* danger zone (admin only) */}
        {isAdmin && (
          <Card className="border-alert-bg">
            <h3 className="text-sm font-semibold text-alert">Delete this business</h3>
            <p className="mt-1 text-sm text-ink-3">
              Permanently erase <span className="font-medium">{biz?.name ?? "this business"}</span> and all of its
              data. This cannot be undone. Type the business name to confirm.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Input
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder={biz?.name ?? "business name"}
                className="w-auto"
              />
              <Button
                variant="danger"
                onClick={deleteBusiness}
                disabled={del.isPending || !biz || confirmText !== biz.name}
              >
                {del.isPending ? "Deleting…" : "Delete business"}
              </Button>
            </div>
            {del.isError && <p className="mt-2 text-xs text-alert">{(del.error as Error)?.message}</p>}
          </Card>
        )}
      </div>
    </div>
  );
}
