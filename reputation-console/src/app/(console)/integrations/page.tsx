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
  useStartGscVerification,
  useCompleteGscVerification,
  useGaProperties,
  useSetGaProperty,
  useZerniaSetup,
  useZerniaConnect,
  useZerniaSync,
  useExtensionTokens,
  useCreateExtensionToken,
  useRevokeExtensionToken,
  useCitationDirectories,
  useSetDirectoryCredentials,
  useCitationRuns,
  useCitationRun,
  useStartCitationRun,
  useConfirmCitationRun,
  useCancelCitationRun,
  useWritingStyles,
  useAnalyzeWritingStyle,
  useSetActiveStyle,
  useDeleteWritingStyle,
} from "@/lib/hooks";
import { Card, PageHeader, Spinner, Pill, Button, Input } from "@/components/ui";
import { EmptyState } from "@/components/primitives";
import { TabNav } from "@/components/content/TabNav";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import type { Connection, ZerniaAccount } from "@/lib/types";
import type { Tone } from "@/lib/uiTokens";
import { ApiError, apiBase } from "@/lib/api";

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
  if (entries.length === 0) return <p className="text-sm text-ink-4">No details.</p>;
  return (
    <dl className="space-y-1">
      {entries.map(([k, v]) => (
        <div key={k} className="grid grid-cols-1 gap-0.5 sm:grid-cols-[160px_1fr]">
          <dt className="text-xs font-medium uppercase tracking-wide text-ink-4">{k.replace(/_/g, " ")}</dt>
          <dd className="text-sm text-ink-2">
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
      // A revoked connection means data collection has STOPPED — surface it as needing attention,
      // not a benign grey, so the owner knows to reconnect (OAuth access was withdrawn/expired).
      return { tone: "bad", label: "Disconnected — reconnect" };
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

// Guided verification: for a site the owner hasn't verified in Search Console yet. Get a code,
// place it (a <head> meta tag for a URL, or a DNS TXT record for a whole domain), then verify —
// we register the property so it becomes selectable. No history exists before verification.
function GscVerifyForm({ businessId, connId }: { businessId: number | null; connId: number }) {
  const start = useStartGscVerification(businessId, connId);
  const complete = useCompleteGscVerification(businessId, connId);
  const [siteUrl, setSiteUrl] = useState("");
  const [method, setMethod] = useState<"META" | "DNS_TXT">("META");
  const [token, setToken] = useState<string | null>(null);
  const [instructions, setInstructions] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const onStart = () => {
    setNote(null);
    setToken(null);
    start.mutate(
      { site_url: siteUrl.trim(), method },
      {
        onSuccess: (r) => { setToken(r.token); setInstructions(r.instructions); },
        onError: (e) => setNote(e instanceof ApiError ? e.message : "Couldn't get a verification code."),
      },
    );
  };

  const onVerify = () => {
    setNote(null);
    complete.mutate(
      { site_url: siteUrl.trim(), method },
      {
        onSuccess: (r) => {
          if (r.verified && r.added) setNote(`Verified — importing ${r.property}. It'll appear above shortly.`);
          else if (r.verified) setNote(r.add_error || "Verified, but couldn't auto-add it — reconnect Search Console and try again.");
          else setNote(r.error || "Not verified yet — give the change a moment, then retry.");
        },
        onError: (e) => setNote(e instanceof ApiError ? e.message : "Verification failed — give DNS/the tag a moment, then retry."),
      },
    );
  };

  const copy = () => {
    if (!token) return;
    navigator.clipboard?.writeText(token);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="mt-2 rounded-md border border-line bg-paper p-3">
      <div className="text-xs font-semibold text-ink-2">Verify a site that isn&apos;t in Search Console yet</div>
      <p className="mt-0.5 text-[11px] text-ink-3">
        Enter the site, get a code, place it, then verify — we register the property for you.
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Input
          value={siteUrl}
          onChange={(e) => setSiteUrl(e.target.value)}
          placeholder="example.com"
          className="min-w-[14rem] flex-1"
        />
        <select
          value={method}
          onChange={(e) => setMethod(e.target.value as "META" | "DNS_TXT")}
          className="rounded-md border border-line-2 px-2 py-1.5 text-sm text-ink-2"
        >
          <option value="META">HTML tag (one website URL)</option>
          <option value="DNS_TXT">DNS record (whole domain)</option>
        </select>
        <Button
          variant="secondary"
          onClick={onStart}
          disabled={start.isPending || !siteUrl.trim()}
        >
          {start.isPending ? "Getting code…" : "Get code"}
        </Button>
      </div>
      {token && (
        <div className="mt-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-4">
              {method === "DNS_TXT" ? "Add this DNS TXT record" : "Add this tag inside <head>"}
            </span>
            <button onClick={copy} className="text-[11px] font-medium text-indigo hover:text-indigo-strong">
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <pre className="mt-1 max-h-28 overflow-auto whitespace-pre-wrap break-all rounded bg-card p-2 font-mono text-[11px] text-ink-2 ring-1 ring-line">{token}</pre>
          {instructions && <p className="mt-1 whitespace-pre-wrap text-[11px] text-ink-3">{instructions}</p>}
          <Button
            className="mt-2"
            onClick={onVerify}
            disabled={complete.isPending}
          >
            {complete.isPending ? "Verifying…" : "I've added it — Verify & connect"}
          </Button>
        </div>
      )}
      {note && <p className="mt-1.5 text-xs text-ink-3">{note}</p>}
    </div>
  );
}

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
  const [showVerify, setShowVerify] = useState(false);

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
    <div className="mt-3 border-t border-line pt-3">
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-4">Search Console property</div>
      {isLoading ? (
        <p className="text-xs text-ink-3">Loading your verified properties…</p>
      ) : error ? (
        <p className="text-xs text-alert">Couldn&apos;t load properties — try Test, or reconnect.</p>
      ) : sites.length === 0 ? (
        <div>
          <p className="text-xs text-ink-3">
            No verified properties on this Google account yet — verify your site below to start importing data.
          </p>
          <GscVerifyForm businessId={businessId} connId={connection.id} />
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={current}
            onChange={(e) => setSelected(e.target.value)}
            className="min-w-[16rem] flex-1 rounded-md border border-line-2 px-3 py-1.5 text-sm text-ink-2"
          >
            <option value="" disabled>Choose a property…</option>
            {sites.map((s) => (
              <option key={s.property} value={s.property}>
                {s.property}
              </option>
            ))}
          </select>
          <Button
            onClick={onSave}
            disabled={save.isPending || !current || current === saved}
          >
            {save.isPending ? "Saving…" : "Save property"}
          </Button>
        </div>
      )}
      {sites.length > 0 && (
        <div className="mt-2">
          <button
            onClick={() => setShowVerify((s) => !s)}
            className="text-[11px] font-medium text-indigo hover:text-indigo-strong"
          >
            {showVerify ? "Hide" : "Don't see your site? Verify a new one"}
          </button>
          {showVerify && <GscVerifyForm businessId={businessId} connId={connection.id} />}
        </div>
      )}
      <p className="mt-1.5 text-[11px] text-ink-4">
        Search Console only has history from when the property was verified.
      </p>
      {note && <p className="mt-1 text-xs text-ink-3">{note}</p>}
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
    <div className="mt-3 border-t border-line pt-3">
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-4">Analytics property</div>
      {isLoading ? (
        <p className="text-xs text-ink-3">Loading your GA4 properties…</p>
      ) : error ? (
        <p className="text-xs text-alert">Couldn&apos;t load properties — try Test, or reconnect.</p>
      ) : properties.length === 0 ? (
        <p className="text-xs text-ink-3">No GA4 properties found on this Google account.</p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={current}
            onChange={(e) => setSelected(e.target.value)}
            className="min-w-[16rem] flex-1 rounded-md border border-line-2 px-3 py-1.5 text-sm text-ink-2"
          >
            <option value="" disabled>Choose a property…</option>
            {properties.map((p) => (
              <option key={p.property} value={p.property}>
                {p.display_name}
                {p.account ? ` · ${p.account}` : ""}
              </option>
            ))}
          </select>
          <Button
            onClick={onSave}
            disabled={save.isPending || !current || current === saved}
          >
            {save.isPending ? "Saving…" : "Save property"}
          </Button>
        </div>
      )}
      <p className="mt-1.5 text-[11px] text-ink-4">
        Conversions only show once you&apos;ve marked the key events (calls, forms, bookings) as conversions in GA4.
      </p>
      {note && <p className="mt-1 text-xs text-ink-3">{note}</p>}
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
            <h3 className="text-base font-semibold tracking-tight text-ink">{provider.name}</h3>
            <Pill tone={tone}>{label}</Pill>
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${provider.surface === "owned" ? "bg-good-bg text-good ring-good/30" : "bg-amber-bg text-amber ring-amber/30"}`}>
              {provider.surface === "owned" ? "You own this — auto-eligible" : "Third-party — draft + you post"}
            </span>
          </div>
          <p className="mt-1 text-sm text-ink-3">{provider.blurb}</p>
          {connection && (
            <p className="mt-1 text-xs text-ink-4">
              Last checked {fmtWhen(connection.last_used_at)}
              {connection.label ? ` · ${connection.label}` : ""}
              {connection.account_ref ? ` · ${connection.account_ref}` : ""}
            </p>
          )}
          {connection?.last_error && (
            <p className="mt-1 text-xs text-alert">Last error: {connection.last_error}</p>
          )}
          {/* GBP review-reply approval gate */}
          {provider.kind === "google_business_profile" && connected && connection?.gbp_access !== "approved" && (
            <p className="mt-1 text-xs text-amber">Review replies need Google&apos;s approval — posting updates works now.</p>
          )}
        </div>

        {canConnect && (
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {connected ? (
              <>
                <Button
                  variant="secondary"
                  onClick={runTest}
                  disabled={test.isPending}
                >
                  {test.isPending ? "Testing…" : "Test"}
                </Button>
                <Button
                  variant="danger"
                  onClick={() => connection && window.confirm(`Disconnect ${provider.name}? Publishing to it will stop until you reconnect.`) && disconnect.mutate(connection.id)}
                  disabled={disconnect.isPending}
                >
                  Disconnect
                </Button>
              </>
            ) : isOauth ? (
              <Button
                onClick={startOauth}
                disabled={authorize.isPending}
              >
                {authorize.isPending ? "Redirecting…" : "Connect with Google"}
              </Button>
            ) : (
              <Button
                onClick={() => { setShowForm((s) => !s); setErr(null); }}
              >
                {showForm ? "Cancel" : "Connect"}
              </Button>
            )}
          </div>
        )}
      </div>

      {testNote && <p className="mt-2 text-xs text-ink-3">{testNote}</p>}

      {/* Direct-credential forms (WordPress app-password / Ayrshare profile key) */}
      {canConnect && showForm && provider.kind === "wordpress_org" && (
        <div className="mt-3 space-y-2 border-t border-line pt-3">
          <p className="text-xs text-ink-3">
            Create an <span className="font-medium">Application Password</span> in WordPress (Users → Profile) and paste it
            here. We only accept secure <span className="font-medium">https://</span> sites.
          </p>
          <Input value={siteUrl} onChange={(e) => setSiteUrl(e.target.value)} placeholder="https://yoursite.com" />
          <div className="flex flex-wrap gap-2">
            <Input value={wpUser} onChange={(e) => setWpUser(e.target.value)} placeholder="WordPress username"
              className="min-w-48 flex-1" />
            <Input value={appPassword} onChange={(e) => setAppPassword(e.target.value)} placeholder="Application password"
              type="password" className="min-w-48 flex-1" />
          </div>
          <Button onClick={submitWordpress} disabled={connect.isPending || !siteUrl || !wpUser || !appPassword}>
            {connect.isPending ? "Saving…" : "Save connection"}
          </Button>
        </div>
      )}
      {canConnect && showForm && provider.kind === "ayrshare_profile" && (
        <div className="mt-3 space-y-2 border-t border-line pt-3">
          <p className="text-xs text-ink-3">
            Paste your Ayrshare <span className="font-medium">Profile Key</span>. Social posts are prepared as drafts —
            you review and post them yourself (third-party platforms require manual posting).
          </p>
          <Input value={profileKey} onChange={(e) => setProfileKey(e.target.value)} placeholder="Ayrshare profile key"
            type="password" />
          <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Display name (optional)" />
          <Button onClick={submitAyrshare} disabled={connect.isPending || !profileKey}>
            {connect.isPending ? "Saving…" : "Save connection"}
          </Button>
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

      {err && <p className="mt-2 text-xs text-alert">{err}</p>}
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
            <h3 className="text-base font-semibold tracking-tight text-ink">Social media (Zernio)</h3>
            <Pill tone={isSetUp ? "good" : "neutral"}>{isSetUp ? "Set up" : "Not set up"}</Pill>
            <span className="rounded-full bg-amber-bg px-2 py-0.5 text-[11px] font-medium text-amber ring-1 ring-inset ring-amber/30">
              Third-party — you authorize each network
            </span>
          </div>
          <p className="mt-1 text-sm text-ink-3">
            Connect the client&apos;s social accounts to publish approved posts.
          </p>
          {isSetUp && connectedCount > 0 && (
            <p className="mt-1 text-xs text-ink-4">
              {connectedCount} of {platforms.length} platform{platforms.length === 1 ? "" : "s"} connected
            </p>
          )}
        </div>

        {canEdit && !isSetUp && (
          <div className="flex shrink-0 items-center gap-2">
            <Button
              onClick={runSetup}
              disabled={setup.isPending}
            >
              {setup.isPending ? "Setting up…" : "Set up social publishing"}
            </Button>
          </div>
        )}
      </div>

      {/* Set up: per-platform connect grid + sync. */}
      {canEdit && isSetUp && (
        <div className="mt-3 border-t border-line pt-3">
          <p className="text-xs text-ink-3">
            Your Zernio profile is ready. Click <span className="font-medium">Connect</span> on each network to authorize
            that account in a Zernio popup, then <span className="font-medium">Sync</span> to confirm.
          </p>

          {platforms.length === 0 ? (
            <p className="mt-3 text-xs text-ink-4">No connectable platforms returned yet.</p>
          ) : (
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {platforms.map((platform) => {
                const handle = handleFor(platform);
                return (
                  <div
                    key={platform}
                    className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2"
                  >
                    <span className="text-sm font-medium text-ink-2">{platformLabel(platform)}</span>
                    {handle ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-good-bg px-2 py-0.5 text-[11px] font-medium text-good ring-1 ring-inset ring-good/30">
                        ✓ connected{handle !== "connected" ? ` as ${handle}` : ""}
                      </span>
                    ) : (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => openConnect(platform)}
                        disabled={connect.isPending && connect.variables === platform}
                      >
                        {connect.isPending && connect.variables === platform ? "Opening…" : "Connect"}
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button
              onClick={runSync}
              disabled={sync.isPending}
            >
              {sync.isPending ? "Syncing…" : "Sync connected accounts"}
            </Button>
            <span className="text-xs text-ink-4">
              After you finish connecting in the popup, click Sync to pull your accounts.
            </span>
          </div>
          {syncNote && <p className="mt-2 text-xs text-ink-3">{syncNote}</p>}
        </div>
      )}

      {err && <p className="mt-2 text-xs text-alert">{err}</p>}
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
        <Card className="mb-4 border-amber/30 bg-amber-bg">
          <div className="text-sm font-semibold text-ink">Connections aren&apos;t configured on this server yet</div>
          <p className="mt-1 text-sm text-ink-2">
            An administrator must set <span className="font-mono text-xs">TOKEN_ENC_KEY</span> before credentials can be
            stored securely. Until then, connecting is disabled.
          </p>
        </Card>
      )}

      <Card className="mb-4 bg-indigo-050/50">
        <div className="text-sm font-semibold text-ink">How publishing honesty works</div>
        <p className="mt-1 text-sm text-ink-2">
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

// ---- Reply Assist (Chrome extension) tab -----------------------------------------------
// Yelp/Reddit/Facebook comment replies are read-only in the console (those platforms' terms
// forbid automated posting, and there's no API to post through anyway). This tab mints a
// revocable bearer token the extension uses to pull already-drafted replies onto the operator's
// own screen while they're looking at the review/comment on the platform's own site — they still
// click "post" themselves, so nothing here touches anyone's terms of service.
function ReplyAssistTab({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const { data, isLoading } = useExtensionTokens(businessId);
  const create = useCreateExtensionToken(businessId);
  const revoke = useRevokeExtensionToken(businessId);
  const [label, setLabel] = useState("Reply Assist extension");
  const [freshToken, setFreshToken] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      <Card className="bg-indigo-050/50">
        <div className="text-sm font-semibold text-ink">What this does</div>
        <p className="mt-1 text-sm text-ink-2">
          A small Chrome extension shows the reply we already drafted for a Yelp, Reddit, or Facebook review/comment right on
          that page, so you can review it and paste it in — the platform still requires you to post it yourself. Generate a
          token below, then paste it into the extension&apos;s options page.
        </p>
      </Card>

      {canEdit && (
        <Card>
          <div className="text-sm font-semibold text-ink">Generate a token</div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Input value={label} onChange={(e) => setLabel(e.target.value)} className="max-w-xs" placeholder="e.g. Logan's laptop" />
            <Button
              onClick={() => create.mutate(label, { onSuccess: (res) => setFreshToken(res.token) })}
              disabled={create.isPending}
            >
              {create.isPending ? "Generating…" : "+ New token"}
            </Button>
          </div>
          {freshToken && (
            <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
                Copy this now — it won&apos;t be shown again
              </div>
              <code className="mt-1 block break-all rounded bg-white px-2 py-1.5 text-xs text-ink">{freshToken}</code>
              <button
                type="button"
                onClick={() => navigator.clipboard?.writeText(freshToken)}
                className="mt-2 text-xs font-medium text-indigo-600 hover:underline"
              >
                Copy to clipboard
              </button>
            </div>
          )}
        </Card>
      )}

      <Card>
        <div className="text-sm font-semibold text-ink">Active tokens</div>
        {isLoading ? (
          <Spinner />
        ) : !data?.tokens.length ? (
          <p className="mt-1 text-sm text-ink-4">No tokens yet.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {data.tokens.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-line px-3 py-2">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-ink">{t.label || "Reply Assist extension"}</div>
                  <div className="text-xs text-ink-4">
                    Created {new Date(t.created_at).toLocaleDateString()}
                    {t.last_used_at ? ` · last used ${new Date(t.last_used_at).toLocaleDateString()}` : " · never used"}
                    {t.revoked_at && " · revoked"}
                  </div>
                </div>
                {canEdit && !t.revoked_at && (
                  <button
                    type="button"
                    onClick={() => revoke.mutate(t.id)}
                    disabled={revoke.isPending}
                    className="text-xs font-medium text-rose-600 hover:underline disabled:opacity-50"
                  >
                    Revoke
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

// ---- Citation builder (computer-use directory listings) tab ---------------------------
// Drives a headless browser under Gemini Computer Use through a directory's own claim/update
// flow, pausing for an explicit confirm before any submit-like click. Always triggered by hand;
// never a background job. See rep_engine.citation_builder for the full safety posture.
function RunViewer({ businessId, runId, onClose }: { businessId: number | null; runId: number; onClose: () => void }) {
  const { data: run } = useCitationRun(businessId, runId);
  const confirm = useConfirmCitationRun(businessId);
  const cancel = useCancelCitationRun(businessId);

  if (!run) return <Spinner />;
  const lastStep = run.steps[run.steps.length - 1];
  const shotUrl = lastStep && businessId != null
    ? `${apiBase()}/businesses/${businessId}/citation-runs/${runId}/screenshot/${lastStep.step}`
    : null;
  const statusWord: Record<string, string> = {
    running: "Running…", awaiting_confirmation: "Waiting on you", done: "Done", failed: "Failed", cancelled: "Cancelled",
  };

  return (
    <Card className="mt-3">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-ink">Run #{run.id} — {statusWord[run.status] || run.status}</div>
        <button type="button" onClick={onClose} className="text-xs text-ink-4 hover:underline">Close</button>
      </div>
      {shotUrl && (
        /* eslint-disable-next-line @next/next/no-img-element */
        <img src={shotUrl} alt={`Step ${lastStep.step}`} className="mt-2 max-h-80 w-auto rounded border border-line" />
      )}
      {run.status === "awaiting_confirmation" && run.pending_action && (
        <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-amber-700">Ready to submit — your call</div>
          <p className="mt-1 text-sm text-ink-2">
            The next action looks like a final submit/claim/publish click: <code className="text-xs">{JSON.stringify(run.pending_action)}</code>.
            Nothing gets sent to the directory until you approve it.
          </p>
          <div className="mt-2 flex gap-2">
            <Button onClick={() => confirm.mutate(runId)} disabled={confirm.isPending}>
              {confirm.isPending ? "Submitting…" : "Approve & continue"}
            </Button>
            <button
              type="button"
              onClick={() => cancel.mutate(runId)}
              disabled={cancel.isPending}
              className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-2 hover:bg-slate-50"
            >
              Cancel run
            </button>
          </div>
        </div>
      )}
      {run.status === "failed" && run.error && (
        <p className="mt-2 text-sm text-rose-600">{run.error}</p>
      )}
      <p className="mt-2 text-xs text-ink-4">{run.steps.length} step{run.steps.length === 1 ? "" : "s"} so far.</p>
    </Card>
  );
}

function CitationBuilderTab({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const { data, isLoading } = useCitationDirectories(businessId);
  const { data: runsData } = useCitationRuns(businessId);
  const setCreds = useSetDirectoryCredentials(businessId);
  const start = useStartCitationRun(businessId);
  const [editingDir, setEditingDir] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [activeRun, setActiveRun] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  if (isLoading || !data) return <Spinner />;

  return (
    <div className="space-y-4">
      <Card className="bg-indigo-050/50">
        <div className="text-sm font-semibold text-ink">What this does</div>
        <p className="mt-1 text-sm text-ink-2">
          Claiming/updating a directory listing (Apple Maps, Bing Places, Nextdoor Business) has no API — it&apos;s pure
          click-through toil. This drives a browser through that flow for you, using your saved login, and pauses right
          before any submit/claim/publish click so you approve it yourself.
        </p>
        {!data.configured && (
          <p className="mt-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-700 ring-1 ring-inset ring-amber-200">
            Not configured yet — set COMPUTER_USE_API_KEY (or GEMINI_API_KEY) and run{" "}
            <code>playwright install chromium</code> on the server to enable.
          </p>
        )}
      </Card>

      <div className="space-y-3">
        {data.directories.map((d) => (
          <Card key={d.key}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-sm font-semibold text-ink">{d.label}</div>
                <div className="text-xs text-ink-4">{d.has_credentials ? "Login saved" : "No login saved yet"}</div>
              </div>
              {canEdit && (
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => { setEditingDir(editingDir === d.key ? null : d.key); setUsername(""); setPassword(""); }}
                    className="rounded-md border border-line px-2.5 py-1 text-xs font-medium text-ink-2 hover:bg-slate-50"
                  >
                    {d.has_credentials ? "Update login" : "Add login"}
                  </button>
                  <Button
                    onClick={() => {
                      setErr(null);
                      start.mutate({ directoryKey: d.key }, {
                        onSuccess: (res) => setActiveRun(res.run_id),
                        onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't start the run."),
                      });
                    }}
                    disabled={!data.configured || !d.has_credentials || start.isPending}
                    title={!d.has_credentials ? "Add a login first" : undefined}
                  >
                    {start.isPending ? "Starting…" : "Start run"}
                  </Button>
                </div>
              )}
            </div>
            {editingDir === d.key && (
              <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-line pt-2">
                <Input placeholder="Username / email" value={username} onChange={(e) => setUsername(e.target.value)} className="max-w-xs" />
                <Input placeholder="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="max-w-xs" />
                <Button
                  onClick={() => setCreds.mutate({ directoryKey: d.key, username, password }, {
                    onSuccess: () => { setEditingDir(null); setUsername(""); setPassword(""); },
                  })}
                  disabled={!username || !password || setCreds.isPending}
                >
                  Save
                </Button>
              </div>
            )}
          </Card>
        ))}
      </div>

      {err && <p className="text-sm text-rose-600">{err}</p>}
      {activeRun != null && <RunViewer businessId={businessId} runId={activeRun} onClose={() => setActiveRun(null)} />}

      {!!runsData?.runs.length && (
        <Card>
          <div className="text-sm font-semibold text-ink">Past runs</div>
          <ul className="mt-2 space-y-1.5">
            {runsData.runs.map((r) => (
              <li key={r.id} className="flex items-center justify-between text-sm">
                <button type="button" onClick={() => setActiveRun(r.id)} className="text-indigo-600 hover:underline">
                  #{r.id} · {r.directory_key} · {r.status}
                </button>
                <span className="text-xs text-ink-4">{new Date(r.updated_at).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
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
      <Card className="mb-4 bg-indigo-050/50">
        <div className="text-sm font-semibold text-ink">What this is for</div>
        <p className="mt-1 text-sm text-ink-2">
          If you already use an SEO or analytics tool (SiteGuru, Screpy, ClickRank, Google Analytics, Search
          Console…), paste its report here. We read the real numbers and fold them into your reputation plan.
        </p>
        <ul className="mt-2 list-disc space-y-1 pl-6 text-sm text-ink-2">
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
        <p className="mt-2 text-xs text-ink-3">
          Paste a report as CSV, JSON, or plain text — we normalize it for you. Optional; you don&apos;t need it to get started.
        </p>
      </Card>

      {canEdit && (
        <Card className="mb-4">
          <div className="mb-2 text-sm font-medium text-ink-2">Add a report</div>
          <div className="flex flex-wrap gap-2">
            <Input
              placeholder="Source (e.g. siteguru)"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="w-auto"
            />
            <select value={type} onChange={(e) => setType(e.target.value)} className="rounded-md border border-line-2 px-3 py-1.5 text-sm text-ink-2">
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
            className="mt-2 w-full rounded-md border border-line-2 px-3 py-2 font-mono text-sm text-ink-2"
          />
          <div className="mt-2 flex items-center gap-2">
            <Button
              disabled={ingest.isPending || !source || !content}
              onClick={() => ingest.mutate({ source, signal_type: type, content }, { onSuccess: () => setContent("") })}
            >
              Upload
            </Button>
            {rawCount > 0 && (
              <Button
                variant="secondary"
                disabled={normalize.isPending}
                onClick={() => normalize.mutate({ jobType: "normalize_signals" })}
              >
                Normalize {rawCount} new with AI
              </Button>
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
                <span className="rounded bg-ink px-1.5 py-0.5 text-xs font-medium text-white">{s.source}</span>
                <span className="text-xs text-ink-3">{TYPE_LABELS[s.signal_type ?? ""] ?? (s.signal_type || "").replace(/_/g, " ")}</span>
                <span className={`text-xs ${s.status === "normalized" ? "text-good" : s.status === "failed" ? "text-alert" : "text-amber"}`}>
                  {STATUS_WORDS[s.status] ?? s.status}
                </span>
                <span className="text-xs text-ink-4">{s.created_at ? new Date(s.created_at).toLocaleDateString() : ""}</span>
              </div>
              {s.normalized ? (
                <div className="mt-2 border-t border-line pt-2">
                  <div className="mb-1 text-xs font-medium uppercase tracking-wide text-ink-4">What we learned</div>
                  <KeyValues data={s.normalized} />
                </div>
              ) : (
                <p className="mt-2 text-xs text-ink-4">
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

// ---- Writing styles tab: clone a brand voice from a URL; the active one shapes generated content ----
function WritingStylesTab({ businessId, canEdit }: { businessId: number | null; canEdit: boolean }) {
  const { data, isLoading } = useWritingStyles(businessId);
  const analyze = useAnalyzeWritingStyle(businessId);
  const setActive = useSetActiveStyle(businessId);
  const del = useDeleteWritingStyle(businessId);
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const styles = data?.styles ?? [];

  return (
    <div className="space-y-4">
      <Card className="bg-indigo-050/50">
        <div className="text-sm font-semibold text-ink">Write in your brand&apos;s voice</div>
        <p className="mt-1 text-sm text-ink-2">
          Paste a URL to an article that sounds like you (yours or a reference). We analyze its style — tone, sentence length, vocabulary, quirks — and the <span className="font-medium">active</span> style shapes every piece we generate.
        </p>
      </Card>

      {canEdit && (
        <Card>
          <div className="text-sm font-semibold text-ink">Clone a style from a URL</div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/an-article" className="min-w-[260px] flex-1" />
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name (optional)" className="max-w-[180px]" />
            <Button
              onClick={() => { setErr(null); analyze.mutate({ url, name: name || undefined }, { onSuccess: () => { setUrl(""); setName(""); }, onError: (e) => setErr(e instanceof ApiError ? e.message : "Couldn't analyze that URL.") }); }}
              disabled={analyze.isPending || !url.trim()}
            >
              {analyze.isPending ? "Analyzing…" : "Analyze style"}
            </Button>
          </div>
          {err && <p className="mt-1.5 text-xs text-rose-600">{err}</p>}
        </Card>
      )}

      <Card>
        <div className="text-sm font-semibold text-ink">Your styles</div>
        {isLoading ? <Spinner /> : styles.length === 0 ? (
          <p className="mt-1 text-sm text-ink-4">No styles yet — analyze a URL above.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {styles.map((s) => (
              <li key={s.id} className={`rounded-lg border p-3 ${s.active ? "border-indigo-300 bg-indigo-050/40" : "border-line"}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-sm font-medium text-ink">
                      {s.name}
                      {s.active && <span className="rounded-full bg-indigo-600 px-2 py-0.5 text-[10px] font-semibold text-white">Active</span>}
                    </div>
                    {s.source_url && <a href={s.source_url} target="_blank" rel="noreferrer" className="text-[11px] text-ink-4 hover:text-indigo hover:underline">{s.source_url}</a>}
                  </div>
                  {canEdit && (
                    <div className="flex items-center gap-2">
                      {s.active ? (
                        <button onClick={() => setActive.mutate(null)} className="text-xs font-medium text-ink-3 hover:underline">Deactivate</button>
                      ) : (
                        <button onClick={() => setActive.mutate(s.id)} className="rounded-md border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-100">Use this</button>
                      )}
                      <button onClick={() => del.mutate(s.id)} className="text-xs font-medium text-rose-600 hover:underline">Delete</button>
                    </div>
                  )}
                </div>
                {s.profile && <p className="mt-1.5 text-[12px] leading-relaxed text-ink-2">{s.profile}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

type Tab = "connections" | "imports" | "reply-assist" | "citations" | "writing-styles";

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

      {/* In-page switch — segmented filter (distinct from the Settings hub's underline tab bar above). */}
      <TabNav
        className="mb-4"
        tabs={[
          { key: "connections", label: "Connections" },
          { key: "imports", label: "Data imports" },
          { key: "reply-assist", label: "Reply Assist extension" },
          { key: "citations", label: "Citation builder" },
          { key: "writing-styles", label: "Writing styles" },
        ]}
        active={tab}
        onSelect={(k) => setTab(k as Tab)}
      />

      {tab === "connections" ? (
        <ConnectionsTab businessId={businessId} canEdit={canEdit} />
      ) : tab === "imports" ? (
        <DataImportsTab businessId={businessId} canEdit={canEdit} />
      ) : tab === "reply-assist" ? (
        <ReplyAssistTab businessId={businessId} canEdit={canEdit} />
      ) : tab === "citations" ? (
        <CitationBuilderTab businessId={businessId} canEdit={canEdit} />
      ) : (
        <WritingStylesTab businessId={businessId} canEdit={canEdit} />
      )}
    </div>
  );
}
