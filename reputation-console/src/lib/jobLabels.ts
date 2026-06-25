// Single source of truth for background-job presentation. Every job_type in the engine's
// JOB_DISPATCH maps to a plain-language label, the navigation group it belongs to (matching
// Sidebar.tsx so "what runs" lines up with "where you see the result"), a one-line hint, and a
// rough typical duration for ETAs. Used by the Run-jobs admin page, the Automation scheduler,
// and the JobProgressBanner so all three speak the same language.

export type JobMeta = {
  type: string;
  label: string; // plain-language, aligned to the nav label of where the result shows up
  navGroup: string; // matches a Sidebar group
  hint?: string; // one short line on what it does
  secs: number; // typical duration, for progress ETA
  internal?: boolean; // automation/maintenance — hidden from the primary trigger grid
};

export const JOB_LABELS: Record<string, JobMeta> = {
  // AI Visibility
  audit: { type: "audit", label: "Run AI visibility audit", navGroup: "AI Visibility", secs: 180,
    hint: "Ask the AI assistants about you and score every answer." },
  refresh_failed: { type: "refresh_failed", label: "Retry failed audit engines", navGroup: "AI Visibility", secs: 120,
    hint: "Re-run only the answers that failed in the latest audit.", internal: true },
  citation_analyze: { type: "citation_analyze", label: "Refresh AI citations", navGroup: "AI Visibility", secs: 45,
    hint: "Recompute which sources AI quotes about you (share of voice)." },
  suggest_prompts: { type: "suggest_prompts", label: "Suggest prompts with AI", navGroup: "AI Visibility", secs: 25,
    hint: "Propose new tracking questions (saved for your review)." },

  // Search & SEO
  site_crawl: { type: "site_crawl", label: "Crawl site (technical SEO)", navGroup: "Search & SEO", secs: 90,
    hint: "Crawl your website for technical / on-page SEO gaps." },
  local_rank: { type: "local_rank", label: "Check local search rankings", navGroup: "Search & SEO", secs: 45,
    hint: "Capture your Google organic + map-pack rank for local searches." },
  benchmark: { type: "benchmark", label: "Benchmark vs competitors", navGroup: "Search & SEO", secs: 300,
    hint: "Measure how often AI surfaces you vs each registered competitor." },

  // Strategy & Plan
  gap_model: { type: "gap_model", label: "Rebuild gap analysis", navGroup: "Strategy & Plan", secs: 60,
    hint: "Re-derive the gaps from the latest audit." },
  plan: { type: "plan", label: "Regenerate plan & tasks", navGroup: "Strategy & Plan", secs: 45,
    hint: "Rebuild the improvement plan (auto-creates the tasks + content to produce)." },
  sync_plan: { type: "sync_plan", label: "Sync plan into tasks", navGroup: "Strategy & Plan", secs: 20,
    hint: "Materialize the plan into trackable work-orders.", internal: true },

  // Content
  production_briefs: { type: "production_briefs", label: "Generate content to produce", navGroup: "Content", secs: 60,
    hint: "Create the video/social content recipes from the plan." },
  generate_drafts: { type: "generate_drafts", label: "Generate content drafts", navGroup: "Content", secs: 120,
    hint: "Draft the owned content the plan calls for (human-reviewed before publishing)." },
  discovery: { type: "discovery", label: "Find outreach targets", navGroup: "Content", secs: 90,
    hint: "Find journalists / outlets / podcasts / communities to reach out to." },
  enrich_outreach: { type: "enrich_outreach", label: "Find contacts for your targets", navGroup: "Content", secs: 90,
    hint: "Best-effort public contact lookup for your outreach targets (you confirm before sending)." },
  social_verify: { type: "social_verify", label: "Check your social profiles", navGroup: "Content", secs: 60,
    hint: "Best-effort check of which social profiles you already have, so recommendations show create vs improve." },

  // Monitor
  mentions_scan: { type: "mentions_scan", label: "Scan for new mentions", navGroup: "Monitor", secs: 60,
    hint: "Search the web for new mentions of your monitored terms." },
  incident_scan: { type: "incident_scan", label: "Scan for incidents", navGroup: "Monitor", secs: 60,
    hint: "Triage negative mentions into incidents with drafted responses." },
  suggest_keywords: { type: "suggest_keywords", label: "Suggest monitoring keywords", navGroup: "Monitor", secs: 25,
    hint: "Propose brand-monitoring keywords for your review." },
  alert_check: { type: "alert_check", label: "Check for alerts", navGroup: "Monitor", secs: 15,
    hint: "Raise proactive alerts (score drop, new negatives, drafts waiting).", internal: true },

  // Proof & reports (retrospective ROI + the client deliverable)
  learn: { type: "learn", label: "Recompute what's working", navGroup: "Proof & reports", secs: 20,
    hint: "Re-learn which tactics moved your score, from your own results.", internal: true },
  report: { type: "report", label: "Build client report", navGroup: "Proof & reports", secs: 60,
    hint: "Generate the monthly client report (reflects everything above)." },

  // Settings / Integrations
  normalize_signals: { type: "normalize_signals", label: "Normalize uploaded data", navGroup: "Settings", secs: 30,
    hint: "Normalize uploaded 3rd-party SEO/SERP reports into signals.", internal: true },

  // Pipeline (the whole monthly run)
  cycle: { type: "cycle", label: "Run full monthly cycle", navGroup: "Overview", secs: 600,
    hint: "Run the whole pipeline: audit → gaps → plan → citations → report." },
};

// Order groups the way the nav does, so the Run-jobs grid reads top-to-bottom like the sidebar.
export const JOB_GROUP_ORDER = [
  "Overview",
  "AI Visibility",
  "Search & SEO",
  "Strategy & Plan",
  "Content",
  "Monitor",
  "Proof & reports",
  "Settings",
];

export function jobMeta(type: string): JobMeta {
  return JOB_LABELS[type] ?? { type, label: type.replace(/_/g, " "), navGroup: "Other", secs: 60 };
}

export function jobLabel(type: string): string {
  return jobMeta(type).label;
}
