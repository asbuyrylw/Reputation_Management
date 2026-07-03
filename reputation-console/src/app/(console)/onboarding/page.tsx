"use client";

import { useState } from "react";
import Link from "next/link";
import { useBusiness } from "@/lib/business";
import { useSetupBusiness, type SetupBusinessVars } from "@/lib/hooks";
import { Card, PageHeader, Pill } from "@/components/ui";
import { TagInput } from "@/components/TagInput";
import { ApiError } from "@/lib/api";

const inputCls =
  "w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 placeholder:text-slate-400";
const labelCls = "block text-sm font-semibold text-slate-800";
const hintCls = "mt-1 text-xs text-slate-500";

const STEPS = ["Business", "Positioning", "Reach", "Review"] as const;

export default function OnboardingPage() {
  const { setBusinessId } = useBusiness();
  const setup = useSetupBusiness();

  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [services, setServices] = useState("");
  const [industry, setIndustry] = useState("");
  const [goal, setGoal] = useState("");
  const [contested, setContested] = useState("");
  const [geo, setGeo] = useState("");
  const [competitors, setCompetitors] = useState<{ name: string; domain: string }[]>([]);
  const [keywords, setKeywords] = useState<string[]>([]);
  const [compName, setCompName] = useState("");
  const [compDomain, setCompDomain] = useState("");
  const [kw, setKw] = useState("");

  const addCompetitor = () => {
    if (!compName.trim()) return;
    setCompetitors((c) => [...c, { name: compName.trim(), domain: compDomain.trim() }]);
    setCompName("");
    setCompDomain("");
  };
  const addKeyword = () => {
    const v = kw.trim();
    if (!v || keywords.includes(v)) return;
    setKeywords((k) => [...k, v]);
    setKw("");
  };

  const canNext = step !== 0 || name.trim().length > 0;

  const launch = () => {
    const vars: SetupBusinessVars = {
      name: name.trim(),
      domain: domain.trim(),
      services: services.trim(),
      industry: industry.trim(),
      goal: goal.trim(),
      contested_terms: contested.trim(),
      geo: geo.trim(),
      competitors,
      keywords,
      run_pipeline: true,
    };
    setup.mutate(vars, {
      onSuccess: (res) => setBusinessId(res.business_id),
    });
  };

  // ---- success screen -----------------------------------------------------
  if (setup.isSuccess && setup.data) {
    const res = setup.data;
    const queued = res.jobs.filter((j) => j.job_id && !j.error);
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader eyebrow="Setup" title="You're all set" />
        <Card accent="good" className="bg-linear-to-br from-emerald-50/60 to-white">
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-100 text-emerald-600">
              <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5"><path fillRule="evenodd" d="M16.7 5.3a1 1 0 010 1.4l-7.5 7.5a1 1 0 01-1.4 0L3.3 9.7a1 1 0 011.4-1.4l3.3 3.3 6.8-6.8a1 1 0 011.4 0z" clipRule="evenodd" /></svg>
            </span>
            <div>
              <h3 className="text-lg font-bold tracking-tight text-slate-900">{res.name} is ready</h3>
              <p className="mt-1 text-sm text-slate-600">
                We saved your profile{res.competitors_added > 0 ? `, ${res.competitors_added} competitor${res.competitors_added === 1 ? "" : "s"}` : ""}
                {res.keywords_added > 0 ? ` and ${res.keywords_added} keyword${res.keywords_added === 1 ? "" : "s"}` : ""}, and kicked off the full pipeline.
              </p>
            </div>
          </div>

          <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Now running</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {queued.length > 0 ? (
                queued.map((j) => (
                  <Pill key={j.job_type} tone="info">
                    <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-500" /> {j.job_type}
                  </Pill>
                ))
              ) : (
                <span className="text-sm text-slate-500">No jobs queued.</span>
              )}
            </div>
            <p className="mt-3 text-xs leading-relaxed text-slate-500">
              We&apos;re running the full board once — audit, SEO crawl, gaps, improvement plan, AI citations,
              competitor benchmark, local rankings, mentions, outreach and content briefs, then your report. It
              runs in the background (~30–50 min); every section fills in as each step finishes.
            </p>
          </div>

          <div className="mt-4 rounded-xl border border-indigo-100 bg-indigo-50/40 p-4">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-indigo-500">In ~30 minutes you&apos;ll be able to see</div>
            <ul className="mt-2 grid grid-cols-1 gap-1.5 text-sm text-slate-700 sm:grid-cols-2">
              <li>📊 Your <Link href="/dashboard" className="font-medium text-indigo-600 hover:underline">score vs your goal</Link></li>
              <li>🎯 Your <Link href="/gaps" className="font-medium text-indigo-600 hover:underline">3 biggest gaps</Link> to fix</li>
              <li>⚔ <Link href="/competitors" className="font-medium text-indigo-600 hover:underline">You vs competitors</Link> in AI answers</li>
              <li>📍 Your <Link href="/seo-overview" className="font-medium text-indigo-600 hover:underline">Google map-pack standing</Link> + rating</li>
              <li>🔑 The <Link href="/seo-overview" className="font-medium text-indigo-600 hover:underline">keywords to rank for</Link></li>
              <li>✅ A <Link href="/next-steps" className="font-medium text-indigo-600 hover:underline">prioritized action plan</Link></li>
            </ul>
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            <Link href="/runs" className="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700">
              Watch progress
            </Link>
            <Link href="/dashboard" className="rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50">
              Go to dashboard
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  // ---- wizard -------------------------------------------------------------
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        eyebrow="Setup"
        title="Set up a new business"
        subtitle="Tell us about the business once. We'll run the full audit, prompts, SEO, gaps, rankings and competitor benchmark for you — no need to visit every page."
      />

      {/* Stepper */}
      <div className="mb-6 flex items-center gap-2">
        {STEPS.map((s, i) => {
          const done = i < step;
          const active = i === step;
          return (
            <div key={s} className="flex flex-1 items-center gap-2">
              <div className="flex items-center gap-2">
                <span
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold transition ${
                    active ? "bg-indigo-600 text-white shadow-sm" : done ? "bg-emerald-500 text-white" : "bg-slate-200 text-slate-500"
                  }`}
                >
                  {done ? "✓" : i + 1}
                </span>
                <span className={`hidden text-sm font-semibold sm:inline ${active ? "text-slate-900" : "text-slate-400"}`}>{s}</span>
              </div>
              {i < STEPS.length - 1 && <div className={`h-0.5 flex-1 rounded ${done ? "bg-emerald-400" : "bg-slate-200"}`} />}
            </div>
          );
        })}
      </div>

      <Card>
        {/* Step 0 — Business */}
        {step === 0 && (
          <div className="space-y-5">
            <div>
              <label className={labelCls}>Business name <span className="text-rose-500">*</span></label>
              <input className={`${inputCls} mt-1.5`} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Cincinnati Wealth Partners" autoFocus />
            </div>
            <div>
              <label className={labelCls}>Website</label>
              <input className={`${inputCls} mt-1.5`} value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="e.g. cincywealth.com" />
              <p className={hintCls}>Used to identify your own content vs. third-party sources.</p>
            </div>
            <div>
              <label className={labelCls}>Industry</label>
              <input className={`${inputCls} mt-1.5`} value={industry} onChange={(e) => setIndustry(e.target.value)} placeholder="e.g. Financial services" />
              <p className={hintCls}>The broad vertical you operate in.</p>
            </div>
            <div>
              <label className={labelCls}>Services / products you offer</label>
              <TagInput
                className="mt-1.5"
                value={services}
                onChange={setServices}
                placeholder="e.g. financial advisors, life insurance, 401k…"
              />
              <p className={hintCls}>Add several keywords (like LinkedIn skills). The first drives your main category search, e.g. “best financial services in your city.”</p>
              <p className={hintCls}>The clearer this is, the sharper every audit and content suggestion.</p>
            </div>
          </div>
        )}

        {/* Step 1 — Positioning */}
        {step === 1 && (
          <div className="space-y-5">
            <div>
              <label className={labelCls}>Your goal — how should AI describe you?</label>
              <textarea className={`${inputCls} mt-1.5 min-h-20 resize-y`} value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="e.g. The most trusted fee-only financial advisor in Cincinnati for retirement planning." />
              <p className={hintCls}>This is the position we measure your AI reputation against.</p>
            </div>
            <div>
              <label className={labelCls}>Anything working against you?</label>
              <textarea className={`${inputCls} mt-1.5 min-h-16 resize-y`} value={contested} onChange={(e) => setContested(e.target.value)} placeholder="e.g. old complaint threads, a name collision with another firm, 'is X a scam' searches" />
              <p className={hintCls}>Narratives, terms, or sources you&apos;re worried AI might repeat. Optional.</p>
            </div>
          </div>
        )}

        {/* Step 2 — Reach */}
        {step === 2 && (
          <div className="space-y-6">
            <div>
              <label className={labelCls}>Areas served</label>
              <input className={`${inputCls} mt-1.5`} value={geo} onChange={(e) => setGeo(e.target.value)} placeholder="e.g. Cincinnati, OH; Northern Kentucky" />
              <p className={hintCls}>Cities/regions you serve — we check local search rankings for these.</p>
            </div>

            {/* Competitors */}
            <div>
              <label className={labelCls}>Competitors</label>
              <div className="mt-1.5 flex flex-wrap gap-2">
                <input className={`${inputCls} min-w-40 flex-1`} value={compName} onChange={(e) => setCompName(e.target.value)} placeholder="Competitor name"
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addCompetitor())} />
                <input className={`${inputCls} min-w-32 flex-1`} value={compDomain} onChange={(e) => setCompDomain(e.target.value)} placeholder="Domain (optional)"
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addCompetitor())} />
                <button type="button" onClick={addCompetitor} className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700">Add</button>
              </div>
              {competitors.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {competitors.map((c, i) => (
                    <span key={i} className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 ring-1 ring-inset ring-slate-200">
                      {c.name}{c.domain ? <span className="text-slate-400">· {c.domain}</span> : null}
                      <button type="button" onClick={() => setCompetitors((cs) => cs.filter((_, j) => j !== i))} className="text-slate-400 hover:text-rose-600" aria-label="remove">×</button>
                    </span>
                  ))}
                </div>
              )}
              <p className={hintCls}>We benchmark how often AI surfaces you vs. each of these.</p>
            </div>

            {/* Keywords */}
            <div>
              <label className={labelCls}>Keywords to track</label>
              <div className="mt-1.5 flex flex-wrap gap-2">
                <input className={`${inputCls} min-w-40 flex-1`} value={kw} onChange={(e) => setKw(e.target.value)} placeholder="e.g. Cincinnati financial advisor"
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addKeyword())} />
                <button type="button" onClick={addKeyword} className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700">Add</button>
              </div>
              {keywords.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {keywords.map((k, i) => (
                    <span key={i} className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 ring-1 ring-inset ring-indigo-200">
                      {k}
                      <button type="button" onClick={() => setKeywords((ks) => ks.filter((_, j) => j !== i))} className="text-indigo-400 hover:text-rose-600" aria-label="remove">×</button>
                    </span>
                  ))}
                </div>
              )}
              <p className={hintCls}>Searches and topics to monitor. You can let AI suggest more later.</p>
            </div>
          </div>
        )}

        {/* Step 3 — Review */}
        {step === 3 && (
          <div className="space-y-4">
            <h3 className="text-base font-semibold tracking-tight text-slate-900">Review &amp; launch</h3>
            <dl className="divide-y divide-slate-100 text-sm">
              {[
                ["Business", name || "—"],
                ["Website", domain || "—"],
                ["Industry", industry || "—"],
                ["Services", services || "—"],
                ["Goal", goal || "—"],
                ["Working against", contested || "—"],
                ["Areas served", geo || "—"],
                ["Competitors", competitors.length ? competitors.map((c) => c.name).join(", ") : "—"],
                ["Keywords", keywords.length ? keywords.join(", ") : "—"],
              ].map(([k, v]) => (
                <div key={k} className="grid grid-cols-3 gap-3 py-2.5">
                  <dt className="font-semibold text-slate-500">{k}</dt>
                  <dd className="col-span-2 text-slate-800">{v}</dd>
                </div>
              ))}
            </dl>
            <div className="rounded-xl bg-indigo-50/60 p-3.5 text-sm text-slate-700 ring-1 ring-inset ring-indigo-100">
              On launch we&apos;ll run the <span className="font-semibold text-slate-900">full pipeline once</span> — audit → SEO crawl → gaps → improvement plan → AI citations → competitor benchmark → local rankings → mentions → outreach → content briefs → report. It runs in the background (~30–50 min) so every section is populated.
            </div>
            {setup.isError && (
              <p className="text-sm font-medium text-rose-600">
                {setup.error instanceof ApiError ? setup.error.message : "Could not complete setup. Please try again."}
              </p>
            )}
          </div>
        )}

        {/* Nav */}
        <div className="mt-7 flex items-center justify-between border-t border-slate-100 pt-4">
          <button
            type="button"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0 || setup.isPending}
            className="rounded-xl px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100 disabled:opacity-40"
          >
            ← Back
          </button>
          {step < STEPS.length - 1 ? (
            <button
              type="button"
              onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
              disabled={!canNext}
              className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-40"
            >
              Continue →
            </button>
          ) : (
            <button
              type="button"
              onClick={launch}
              disabled={setup.isPending || !name.trim()}
              className="rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700 disabled:opacity-50"
            >
              {setup.isPending ? "Setting up…" : "Launch full setup"}
            </button>
          )}
        </div>
      </Card>
    </div>
  );
}
