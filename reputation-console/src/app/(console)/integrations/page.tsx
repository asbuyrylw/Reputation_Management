"use client";

import { useState } from "react";
import { useBusiness } from "@/lib/business";
import {
  useExternalSignals,
  useIngestSignal,
  useTriggerJob,
  useConnections,
  useAuthorizeConnection,
  useConnectDirect,
  useTestConnection,
  useDisconnectConnection,
  useGscSites,
  useSetGscProperty,
  useGaProperties,
  useSetGaProperty,
  useZerniaSetup,
  useZerniaConnect,
  useZerniaSync,
} from "@/lib/hooks";
import { Card, PageHeader, Spinner, Pill } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import type { Connection, ZerniaAccount } from "@/lib/types";
import type { Tone } from "@/lib/uiTokens";
import { ApiError } from "@/lib/api";

const TYPES = ["technical_seo", "keywords", "serp_rank", "backlinks", "brand", "visitors", "other"];
const TYPE_LABELS: Record<string, string> = {
  technical_seo: "Technical SEO health",
  keywords: "Keywords",
  serp_rank: "Google ranking",
  backlinks: "Links to your site",
  brand: "Brand mentions",
  visitors: "Website visitors",
  other: "Other",
};
const STATUS_WORDS: Record<string, string> = {
  raw: "Ready to process",
  normalized: "Processed",
  failed: "Couldn't read this",
};

// Clean key/value render of a normalized report (replaces the raw JSON dump).
function KeyValues({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([, v]) => v != null && v !== "");
  if (entries.length === 0) return <p className="text-sm text-slate-400">No details.</p>;
  return (
    <dl className="space-y-1">
      {entries.map(([k, v]) => (
        <div key={k} className="grid grid-cols-1 gap-0.5 sm:grid-cols-[160px_1fr]">
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">{k.replace(/_/g, " ")}</dt>
          <dd className="text-sm text-slate-700">
            {Array.isArray(v) ? v.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join(", ")
              : typeof v === "object" ? JSON.stringify(v) : String(v)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

// ---- Connections tab ------------------------------------------------------------------

// Map a connection status to a semantic tone + plain label for the status Pill.
function statusTone(status: string): { tone: Tone; label: string } {
  switch (status) {
    case "active":
      return { tone: "good", label: "Connected" };
    case "pending":
      return { tone: "info", label: "Pending" };
    case "error":
      return { tone: "bad", label: "Error" };
    case "revoked":
      return { tone: "neutral", label: "Revoked" };
    case "expired":
      return { tone: "bad", label: "Expired" };
    case "needs_reconnect":
      return { tone: "bad", label: "Reconnect needed" };
    default:
      return { tone: "neutral", label: status || "Not connected" };
  }
}

const fmtWhen = (d?: string | null) => (d ? new Date(d).toLocaleString() : "never");

interface ProviderDef {
  kind: "wordpress_org" | "google_business_profile" | "ayrshare_profile" | "google_search_console" | "google_analytics";
  name: string;
  blurb: string;
  surface: "owned" | "third_party";
}

const PROVIDERS: ProviderDef[] = [
  {
    kind: "wordpress_org",
    name: "WordPress (self-hosted)",
    blurb: "Your own site — approved content can be published straight to it (auto-eligible).",
    surface: "owned",
  },
  {
    kind: "google_business_profile",
    name: "Google Business Profile",
    blurb: "Post updates to your Google profile and reply to Google reviews (subject to Google approval).",
    surface: "owned",
  },
  {
    kind: "ayrshare_profile",
    name: "Social (Facebook · Instagram · LinkedIn · Pinterest)",
    blurb: "Third-party social via Ayrshare — drafts are prepared; you post and confirm manually.",
    surface: "third_party",
  },
  {
    kind: "google_search_console",
    name: "Google Search Console",
    blurb: "Import real Google clicks, impressions & ranking — the proof your SEO is working.",
    surface: "owned",
  },
  {
    kind: "google_analytics",
    name: "Google Analytics",
    blurb: "Import sessions, conversions & behavior — see what visitors do after they arrive.",
    surface: "owned",
  },
];

// Property picker (GSC only): once a Search Console connection exists, choose which verified
// property to pull data from. Reads the saved value off connection.meta.gsc_property; saving
// invalidates the connection + every GSC query. Gated to canEdit by the parent.
function GscPropertyPicker({
  connection,
  businessId,
}: {
  connection: Connection;
  businessId: number | null;
}) {
  const { data, isLoading, error } = useGscSites(businessId, connection.id);
  const save = useSetGscProperty(businessId, connection.id);
  const saved = (connection.meta?.gsc_property as string | undefined) ?? "";
  const [selected, setSelected] = useState<string>(saved);
  const [note, setNote] = useState<string | null>(null);

  const sites = data?.sites ?? [];
  const current = selected || saved;

  const onSave = () => {
    if (!current) return;
    setNote(null);
    save.mutate(current, {
      onSuccess: () => setNote("Saved — importing this property's data."),
      onError: (e) => setNote(e instanceof ApiError ? e.message : "Couldn't save the property."),
    });
  };

  return (
    <div className="mt-3 border-t border-slate-100 pt-3">
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Search Console property</div>
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading your verified properties…</p>
      ) : error ? (
        <p className="text-xs text-rose-600">Couldn&apos;t load properties — try Test, or reconnect.</p>
      ) : sites.length === 0 ? (
        <p className="text-xs text-slate-500">No verified properties found on this Google account.</p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={current}
            onChange={(e) => setSelected(e.target.value)}
            className="min-w-[16rem] flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          >
            <option value="" disabled>Choose a property…</option>
            {sites.map((s) => (
              <option key={s.property} value={s.property}>
                {s.property}
              </option>
            ))}
          </select>
          <button
            onClick={onSave}
            disabled={save.isPending || !current || current === saved}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {save.isPending ? "Saving…" : "Save property"}
          </button>
        </div>
      )}
      <p className="mt-1.5 text-[11px] text-slate-400">
        Search Console only has history from when the property was verified.
      </p>
      {note && <p className="mt-1 text-xs text-slate-500">{note}</p>}
    </div>
  );
}

// Property picker (GA only): once a Google Analytics connection exists, choose which GA4
// property to pull data from. Reads the saved value off connection.meta.ga_property; the
// option label is the property's display_name but the saved value is the property id. Saving
// invalidates the connection + every GA query. Gated to canEdit by the parent.
function GaPropertyPicker({
  connection,
  businessId,
}: {
  connection: Connection;
  businessId: number | null;
}) {
  const { data, isLoading, error } = useGaProperties(businessId, connection.id);
  const save = useSetGaProperty(businessId, connection.id);
  const saved = (connection.meta?.ga_property as string | undefined) ?? "";
  const [selected, setSelected] = useState<string>(saved);
  const [note, setNote] = useState<string | null>(null);

  const properties = data?.properties ?? [];
  const current = selected || saved;

  const onSave = () => {
    if (!current) return;
    setNote(null);
    save.mutate(current, {
      onSuccess: () => setNote("Saved — importing this property's data."),
      onError: (e) => setNote(e instanceof ApiError ? e.message : "Couldn't save the property."),
    });
  };

  return (
    <div className="mt-3 border-t border-slate-100 pt-3">
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Analytics property</div>
      {isLoading ? (
        <p className="text-xs text-slate-500">Loading your GA4 properties…</p>
      ) : error ? (
        <p className="text-xs text-rose-600">Couldn&apos;t load properties — try Test, or reconnect.</p>
      ) : properties.length === 0 ? (
        <p className="text-xs text-slate-500">No GA4 properties found on this Google account.</p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={current}
            onChange={(e) => setSelected(e.target.value)}
            className="min-w-[16rem] flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          >
            <option value="" disabled>Choose a property…</option>
            {properties.map((p) => (
              <option key={p.property} value={p.property}>
                {p.display_name}
                {p.account ? ` · ${p.account}` : ""}
              </option>
            ))}
          </select>
          <button
            onClick={onSave}
            disabled={save.isPending || !current || current === saved}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {save.isPending ? "Saving…" : "Save property"}
          </button>
        </div>
      )}
      <p className="mt-1.5 text-[11px] text-slate-400">
        Conversions only show once you&apos;ve marked the key events (calls, forms, bookings) as conversions in GA4.
      </p>
      {note && <p className="mt-1 text-xs text-slate-500">{note}</p>}
    </div>
  );
}

// A single provider card: status, last-checked, and connect/test/disconnect (canEdit + vault-gated).
function ProviderCard({
  provider,
  connection,
  businessId,
  canEdit,
  vaultReady,
}: {
  provider: ProviderDef;
  connection: Connection | undefined;
  businessId: number | null;
  canEdit: boolean;
  vaultReady: boolean;
}) {
  const authorize = useAuthorizeConnection(businessId);
  const connect = useConnectDirect(businessId);
  const test = useTestConnection(businessId);
  const disconnect = useDisconnectConnection(businessId);
  const [showForm, setShowForm] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [testNote, setTestNote] = useState<string | null>(null);

  // WordPress form
  const [siteUrl, setSiteUrl] = useState("");
  const [wpUser, setWpUser] = useState("");
  const [appPassword, setAppPassword] = useState("");
  // Ayrshare form
  const [profileKey, setProfileKey] = useState("");
  const [displayName, setDisplayName] = useState("");

  const status = connection?.status ?? "";
  const { tone, label } = statusTone(status);
  const connected = status === "active";
  const canConnect = canEdit && vaultReady;

  // OAuth start, used by all Google providers (GBP + Search Console + Analytics).
  const isOauth =
    provider.kind === "google_business_profile" ||
    provider.kind === "google_search_console" ||
    provider.kind === "google_analytics";
  const startOauth = () => {
    setErr(null);
    authorize.mutate(provider.kind, {
      onSuccess: (res) => {
        if (res.authorize_url) window.location.href = res.authorize_url;
      },
      onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't start the connection."),
    });
  };

  const submitWordpress = () => {
    setErr(null);
    if (!/^https:\/\//i.test(siteUrl.trim())) {
      setErr("Site URL must start with https:// for a secure connection.");
      return;
    }
    connect.mutate(
      { kind: "wordpress_org", site_url: siteUrl.trim(), wp_user: wpUser.trim(), app_password: appPassword.trim() },
      {
        onSuccess: () => {
          setShowForm(false);
          setSiteUrl(""); setWpUser(""); setAppPassword("");
        },
        onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't save the connection."),
      },
    );
  };

  const submitAyrshare = () => {
    setErr(null);
    connect.mutate(
      { kind: "ayrshare_profile", profile_key: profileKey.trim(), display_name: displayName.trim() || undefined },
      {
        onSuccess: () => {
          setShowForm(false);
          setProfileKey(""); setDisplayName("");
        },
        onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't save the connection."),
      },
    );
  };

  const runTest = () => {
    if (!connection) return;
    setTestNote(null);
    test.mutate(connection.id, {
      onSuccess: (res) => setTestNote(res.ok ? `OK — ${res.status}` : `Failed — ${res.detail || res.status}`),
      onError: (e) => setTestNote(e instanceof ApiError ? e.message : "Test failed."),
    });
  };

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold tracking-tight text-slate-900">{provider.name}</h3>
            <Pill tone={tone}>{label}</Pill>
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${provider.surface === "owned" ? "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200" : "bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200"}`}>
              {provider.surface === "owned" ? "You own this — auto-eligible" : "Third-party — draft + you post"}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-600">{provider.blurb}</p>
          {connection && (
            <p className="mt-1 text-xs text-slate-400">
              Last checked {fmtWhen(connection.last_used_at)}
              {connection.label ? ` · ${connection.label}` : ""}
              {connection.account_ref ? ` · ${connection.account_ref}` : ""}
            </p>
          )}
          {connection?.last_error && (
            <p className="mt-1 text-xs text-rose-600">Last error: {connection.last_error}</p>
          )}
          {/* GBP review-reply approval gate */}
          {provider.kind === "google_business_profile" && connected && connection?.gbp_access !== "approved" && (
            <p className="mt-1 text-xs text-amber-700">Review replies need Google&apos;s approval — posting updates works now.</p>
          )}
        </div>

        {canConnect && (
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {connected ? (
              <>
                <button
                  onClick={runTest}
                  disabled={test.isPending}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-50"
                >
                  {test.isPending ? "Testing…" : "Test"}
                </button>
                <button
                  onClick={() => connection && window.confirm(`Disconnect ${provider.name}? Publishing to it will stop until you reconnect.`) && disconnect.mutate(connection.id)}
                  disabled={disconnect.isPending}
                  className="rounded-md border border-rose-200 px-3 py-1.5 text-sm text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                >
                  Disconnect
                </button>
              </>
            ) : isOauth ? (
              <button
                onClick={startOauth}
                disabled={authorize.isPending}
                className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
              >
                {authorize.isPending ? "Redirecting…" : "Connect with Google"}
              </button>
            ) : (
              <button
                onClick={() => { setShowForm((s) => !s); setErr(null); }}
                className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
              >
                {showForm ? "Cancel" : "Connect"}
              </button>
            )}
          </div>
        )}
      </div>

      {testNote && <p className="mt-2 text-xs text-slate-500">{testNote}</p>}

      {/* Direct-credential forms (WordPress app-password / Ayrshare profile key) */}
      {canConnect && showForm && provider.kind === "wordpress_org" && (
        <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
          <p className="text-xs text-slate-500">
            Create an <span className="font-medium">Application Password</span> in WordPress (Users → Profile) and paste it
            here. We only accept secure <span className="font-medium">https://</span> sites.
          </p>
          <input value={siteUrl} onChange={(e) => setSiteUrl(e.target.value)} placeholder="https://yoursite.com"
            className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
          <div className="flex flex-wrap gap-2">
            <input value={wpUser} onChange={(e) => setWpUser(e.target.value)} placeholder="WordPress username"
              className="min-w-[12rem] flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
            <input value={appPassword} onChange={(e) => setAppPassword(e.target.value)} placeholder="Application password"
              type="password" className="min-w-[12rem] flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
          </div>
          <button onClick={submitWordpress} disabled={connect.isPending || !siteUrl || !wpUser || !appPassword}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50">
            {connect.isPending ? "Saving…" : "Save connection"}
          </button>
        </div>
      )}
      {canConnect && showForm && provider.kind === "ayrshare_profile" && (
        <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
          <p className="text-xs text-slate-500">
            Paste your Ayrshare <span className="font-medium">Profile Key</span>. Social posts are prepared as drafts —
            you review and post them yourself (third-party platforms require manual posting).
          </p>
          <input value={profileKey} onChange={(e) => setProfileKey(e.target.value)} placeholder="Ayrshare profile key"
            type="password" className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Display name (optional)"
            className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
          <button onClick={submitAyrshare} disabled={connect.isPending || !profileKey}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50">
            {connect.isPending ? "Saving…" : "Save connection"}
          </button>
        </div>
      )}

      {/* GSC property picker — choose which verified property to pull, once connected. */}
      {provider.kind === "google_search_console" && connected && connection && canConnect && (
        <GscPropertyPicker connection={connection} businessId={businessId} />
      )}

      {/* GA property picker — choose which GA4 property to pull, once connected. */}
      {provider.kind === "google_analytics" && connected && connection && canConnect && (
        <GaPropertyPicker connection={connection} businessId={businessId} />
      )}

      {err && <p className="mt-2 text-xs text-rose-600">{err}</p>}
    </Card>
  );
}

// Human-friendly labels for the Zernio platform slugs (falls back to a capitalized slug).
const ZERNIA_PLATFORM_LABELS: Record<string, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  linkedin: "LinkedIn",
  twitter: "X (Twitter)",
  pinterest: "Pinterest",
  tiktok: "TikTok",
  youtube: "YouTube",
  threads: "Threads",
  bluesky: "Bluesky",
};
const platformLabel = (slug: string) =>
  ZERNIA_PLATFORM_LABELS[slug] ?? slug.charAt(0).toUpperCase() + slug.slice(1);

// Social media (Zernio) card: the connect-your-accounts flow. The owner sets up a profile,
// then per-platform clicks "Connect" (opens a Zernio OAuth popup to authorize that account),
// then "Sync" to pull the connected accounts back. Auth is a server-side account key — there's
// nothing to paste — but we still gate the whole card on canEdit like the other providers.
function ZernioCard({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const { data } = useConnections(businessId);
  const setup = useZerniaSetup(businessId);
  const connect = useZerniaConnect(businessId);
  const sync = useZerniaSync(businessId);
  const [err, setErr] = useState<string | null>(null);
  // Accounts confirmed by the latest in-session sync (merged with what's on the connection meta).
  const [syncedAccounts, setSyncedAccounts] = useState<ZerniaAccount[] | null>(null);
  const [syncNote, setSyncNote] = useState<string | null>(null);

  const connection = data?.connections.find((c) => c.kind === "zernia");
  // platforms come back from setup; once set up they're stored on the connection meta too.
  const setupPlatforms = setup.data?.platforms ?? [];
  const metaPlatforms = (connection?.meta?.platforms as string[] | undefined) ?? [];
  const platforms = setupPlatforms.length ? setupPlatforms : metaPlatforms;

  // platform -> handle/id for connected accounts: prefer the live sync, fall back to meta.accounts.
  const metaAccounts = (connection?.meta?.accounts as Record<string, string> | undefined) ?? {};
  const handleFor = (platform: string): string | null => {
    const synced = syncedAccounts?.find((a) => a.platform === platform && a.is_active);
    if (synced) return synced.username ? `@${synced.username}` : synced.display_name ?? "connected";
    return metaAccounts[platform] ? "connected" : null;
  };
  const isConnected = (platform: string) => handleFor(platform) != null;
  const connectedCount = platforms.filter(isConnected).length;

  const isSetUp = !!connection || setup.isSuccess;

  const runSetup = () => {
    setErr(null);
    setup.mutate(undefined, {
      onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't set up social publishing."),
    });
  };

  const openConnect = (platform: string) => {
    setErr(null);
    connect.mutate(platform, {
      onSuccess: (res) => {
        if (res.authUrl) {
          const w = window.open(res.authUrl, "_blank");
          if (!w) setErr("Your browser blocked the authorization popup — allow popups for this site and try again.");
        }
      },
      onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't start the connection."),
    });
  };

  const runSync = () => {
    setErr(null);
    setSyncNote(null);
    sync.mutate(undefined, {
      onSuccess: (res) => {
        setSyncedAccounts(res.accounts);
        setSyncNote(
          res.accounts.length
            ? `Synced — ${res.connected_platforms.length} platform${res.connected_platforms.length === 1 ? "" : "s"} connected.`
            : "Synced — no connected accounts found yet. Finish authorizing in the popup, then Sync again.",
        );
      },
      onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't sync your accounts."),
    });
  };

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold tracking-tight text-slate-900">Social media (Zernio)</h3>
            <Pill tone={isSetUp ? "good" : "neutral"}>{isSetUp ? "Set up" : "Not set up"}</Pill>
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 ring-1 ring-inset ring-amber-200">
              Third-party — you authorize each network
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-600">
            Connect the client&apos;s social accounts to publish approved posts.
          </p>
          {isSetUp && connectedCount > 0 && (
            <p className="mt-1 text-xs text-slate-400">
              {connectedCount} of {platforms.length} platform{platforms.length === 1 ? "" : "s"} connected
            </p>
          )}
        </div>

        {canEdit && !isSetUp && (
          <div className="flex shrink-0 items-center gap-2">
            <button
              onClick={runSetup}
              disabled={setup.isPending}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {setup.isPending ? "Setting up…" : "Set up social publishing"}
            </button>
          </div>
        )}
      </div>

      {/* Set up: per-platform connect grid + sync. */}
      {canEdit && isSetUp && (
        <div className="mt-3 border-t border-slate-100 pt-3">
          <p className="text-xs text-slate-500">
            Your Zernio profile is ready. Click <span className="font-medium">Connect</span> on each network to authorize
            that account in a Zernio popup, then <span className="font-medium">Sync</span> to confirm.
          </p>

          {platforms.length === 0 ? (
            <p className="mt-3 text-xs text-slate-400">No connectable platforms returned yet.</p>
          ) : (
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {platforms.map((platform) => {
                const handle = handleFor(platform);
                return (
                  <div
                    key={platform}
                    className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2"
                  >
                    <span className="text-sm font-medium text-slate-700">{platformLabel(platform)}</span>
                    {handle ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200">
                        ✓ connected{handle !== "connected" ? ` as ${handle}` : ""}
                      </span>
                    ) : (
                      <button
                        onClick={() => openConnect(platform)}
                        disabled={connect.isPending && connect.variables === platform}
                        className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
                      >
                        {connect.isPending && connect.variables === platform ? "Opening…" : "Connect"}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              onClick={runSync}
              disabled={sync.isPending}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {sync.isPending ? "Syncing…" : "Sync connected accounts"}
            </button>
            <span className="text-xs text-slate-400">
              After you finish connecting in the popup, click Sync to pull your accounts.
            </span>
          </div>
          {syncNote && <p className="mt-2 text-xs text-slate-500">{syncNote}</p>}
        </div>
      )}

      {err && <p className="mt-2 text-xs text-rose-600">{err}</p>}
    </Card>
  );
}

function ConnectionsTab({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const { data, isLoading } = useConnections(businessId);

  if (isLoading || !data) return <Spinner />;

  const byKind: Record<string, Connection | undefined> = {};
  for (const c of data.connections) if (!byKind[c.kind]) byKind[c.kind] = c;

  return (
    <div>
      {!data.vault_ready && (
        <Card className="mb-4 border-amber-200 bg-amber-50/50">
          <div className="text-sm font-semibold text-slate-900">Connections aren&apos;t configured on this server yet</div>
          <p className="mt-1 text-sm text-slate-700">
            An administrator must set <span className="font-mono text-xs">TOKEN_ENC_KEY</span> before credentials can be
            stored securely. Until then, connecting is disabled.
          </p>
        </Card>
      )}

      <Card className="mb-4 bg-indigo-50/50">
        <div className="text-sm font-semibold text-slate-900">How publishing honesty works</div>
        <p className="mt-1 text-sm text-slate-700">
          <span className="font-medium">Surfaces you own</span> (your WordPress site, your Google Business Profile) can be
          published to automatically once you approve. <span className="font-medium">Third-party platforms</span> (Facebook,
          Instagram, LinkedIn, Pinterest) are draft-only — we prepare the post and alert you, but{" "}
          <span className="font-medium">you post it manually</span> to stay within each platform&apos;s terms of service.
        </p>
      </Card>

      <div className="space-y-3">
        {PROVIDERS.map((p) => (
          <ProviderCard
            key={p.kind}
            provider={p}
            connection={byKind[p.kind]}
            businessId={businessId}
            canEdit={canEdit}
            vaultReady={data.vault_ready}
          />
        ))}
        {/* Zernio social publishing — its own connect-your-accounts flow (no vault secret to paste). */}
        <ZernioCard businessId={businessId} canEdit={canEdit} />
      </div>
    </div>
  );
}

// ---- Data imports tab (the original page content) -------------------------------------
function DataImportsTab({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const { data, isLoading } = useExternalSignals(businessId);
  const ingest = useIngestSignal(businessId);
  const normalize = useTriggerJob(businessId);
  const [source, setSource] = useState("");
  const [type, setType] = useState("technical_seo");
  const [content, setContent] = useState("");

  if (isLoading || !data) return <Spinner />;
  const rawCount = data.filter((s) => s.status === "raw").length;

  return (
    <div>
      <Card className="mb-4 bg-indigo-50/50">
        <div className="text-sm font-semibold text-slate-900">What this is for</div>
        <p className="mt-1 text-sm text-slate-700">
          If you already use an SEO or analytics tool (SiteGuru, Screpy, ClickRank, Google Analytics, Search
          Console…), paste its report here. We read the real numbers and fold them into your reputation plan.
        </p>
        <ul className="mt-2 list-disc space-y-1 pl-6 text-sm text-slate-700">
          <li>
            <span className="font-medium">How it&apos;s used:</span> your real Google rankings, backlinks,
            technical-SEO issues, and traffic feed the gap model and site audit — so the plan targets what actually
            needs work instead of guessing.
          </li>
          <li>
            <span className="font-medium">The value:</span> sharper, evidence-based priorities (fix the pages and
            keywords that genuinely move your AI visibility) and hard numbers to prove progress over time.
          </li>
        </ul>
        <p className="mt-2 text-xs text-slate-500">
          Paste a report as CSV, JSON, or plain text — we normalize it for you. Optional; you don&apos;t need it to get started.
        </p>
      </Card>

      {canEdit && (
        <Card className="mb-4">
          <div className="mb-2 text-sm font-medium text-slate-700">Add a report</div>
          <div className="flex flex-wrap gap-2">
            <input
              placeholder="Source (e.g. siteguru)"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
            <select value={type} onChange={(e) => setType(e.target.value)} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm">
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {TYPE_LABELS[t] ?? t.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
          <textarea
            placeholder="Paste the report (CSV / JSON / text)…"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={5}
            className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm"
          />
          <div className="mt-2 flex items-center gap-2">
            <button
              disabled={ingest.isPending || !source || !content}
              onClick={() => ingest.mutate({ source, signal_type: type, content }, { onSuccess: () => setContent("") })}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              Upload
            </button>
            {rawCount > 0 && (
              <button
                disabled={normalize.isPending}
                onClick={() => normalize.mutate({ jobType: "normalize_signals" })}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
              >
                Normalize {rawCount} new with AI
              </button>
            )}
          </div>
        </Card>
      )}

      {data.length === 0 ? (
        <EmptyState
          title="No reports added yet"
          why="You don't need this to get started — but if you have data from another tool, it sharpens your plan."
          produces="Uploaded reports appear here once we've read them, with a plain summary of what we learned."
        />
      ) : (
        <div className="space-y-3">
          {data.map((s) => (
            <Card key={s.id}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-slate-900 px-1.5 py-0.5 text-xs font-medium text-white">{s.source}</span>
                <span className="text-xs text-slate-500">{TYPE_LABELS[s.signal_type ?? ""] ?? (s.signal_type || "").replace(/_/g, " ")}</span>
                <span className={`text-xs ${s.status === "normalized" ? "text-emerald-700" : s.status === "failed" ? "text-rose-700" : "text-amber-700"}`}>
                  {STATUS_WORDS[s.status] ?? s.status}
                </span>
                <span className="text-xs text-slate-400">{s.created_at ? new Date(s.created_at).toLocaleDateString() : ""}</span>
              </div>
              {s.normalized ? (
                <div className="mt-2 border-t border-slate-100 pt-2">
                  <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">What we learned</div>
                  <KeyValues data={s.normalized} />
                </div>
              ) : (
                <p className="mt-2 text-xs text-slate-400">
                  {s.status === "raw" ? "Ready to process — click ‘Normalize’ above." : "We couldn't read this report. Try pasting it as plain text."}
                </p>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

type Tab = "connections" | "imports";

export default function IntegrationsPage() {
  const { businessId, canEdit } = useBusiness();
  const [tab, setTab] = useState<Tab>("connections");

  return (
    <div>
      <PageHeader
        title="Integrations"
        subtitle="Connect the places you publish, and fold in data from other tools."
      />

      <JobProgressBanner businessId={businessId} className="mb-4" />

      {/* tabs */}
      <div className="mb-4 flex gap-1 border-b border-slate-200">
        {([
          { key: "connections", label: "Connections" },
          { key: "imports", label: "Data imports" },
        ] as { key: Tab; label: string }[]).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
              tab === t.key
                ? "border-indigo-600 text-indigo-700"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "connections" ? (
        <ConnectionsTab businessId={businessId} canEdit={canEdit} />
      ) : (
        <DataImportsTab businessId={businessId} canEdit={canEdit} />
      )}
    </div>
  );
}
