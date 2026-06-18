"use client";

import type { Challenge, ChallengeProfile, ChallengeEngine } from "@/lib/types";
import { Card } from "./ui";

const BADGE: Record<ChallengeProfile, string> = {
  awareness_gap: "bg-indigo-50 text-indigo-700 border-indigo-200",
  negative_narrative: "bg-rose-50 text-rose-700 border-rose-200",
  mixed: "bg-amber-50 text-amber-700 border-amber-200",
  established_positive: "bg-green-50 text-green-700 border-green-200",
  unknown: "bg-gray-100 text-gray-500 border-gray-200",
};

// Per-engine row: the challenge is often bimodal (one engine doesn't know the business,
// another knows it and is unfavorable). Showing each engine prevents a single portfolio
// label from hiding that.
function EngineRow({ name, e }: { name: string; e: ChallengeEngine }) {
  const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);
  return (
    <div className="flex items-center justify-between gap-3 py-1.5 text-sm">
      <div className="flex items-center gap-2">
        <span className="font-medium text-gray-700">{ENGINE_LABELS[name] ?? name}</span>
        <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${BADGE[e.profile]}`}>
          {e.label}
        </span>
      </div>
      <div className="flex items-center gap-4 tabular-nums text-xs text-gray-500">
        <span title="Recognition gap (doesn't know the business / wrong entity)">
          gap <span className="text-indigo-600">{pct(e.recognition_gap)}</span>
        </span>
        <span title="Genuinely unfavorable framing">
          neg <span className="text-rose-600">{pct(e.negative_score)}</span>
        </span>
      </div>
    </div>
  );
}

const ENGINE_LABELS: Record<string, string> = {
  openai_search: "ChatGPT",
  anthropic: "Claude",
  perplexity: "Perplexity",
  gemini: "Gemini",
};

// Per-profile presentation: accent color + a plain "how fast" read. The strategic point
// is that an awareness void fills FASTER than an entrenched negative narrative crowds out,
// so the card states the speed implication explicitly.
const STYLE: Record<
  ChallengeProfile,
  { badge: string; accent: string; speed: string; speedTone: string }
> = {
  awareness_gap: {
    badge: "bg-indigo-50 text-indigo-700 border-indigo-200",
    accent: "text-indigo-700",
    speed: "Faster to fix",
    speedTone: "bg-green-50 text-green-700 border-green-200",
  },
  negative_narrative: {
    badge: "bg-rose-50 text-rose-700 border-rose-200",
    accent: "text-rose-700",
    speed: "Slower to fix",
    speedTone: "bg-amber-50 text-amber-700 border-amber-200",
  },
  mixed: {
    badge: "bg-amber-50 text-amber-700 border-amber-200",
    accent: "text-amber-700",
    speed: "Two-track",
    speedTone: "bg-amber-50 text-amber-700 border-amber-200",
  },
  established_positive: {
    badge: "bg-green-50 text-green-700 border-green-200",
    accent: "text-green-700",
    speed: "Defend",
    speedTone: "bg-green-50 text-green-700 border-green-200",
  },
  unknown: {
    badge: "bg-gray-100 text-gray-500 border-gray-200",
    accent: "text-gray-600",
    speed: "Pending audit",
    speedTone: "bg-gray-100 text-gray-500 border-gray-200",
  },
};

function Track({
  label,
  pct,
  color,
  note,
}: {
  label: string;
  pct: number | null;
  color: string;
  note: string;
}) {
  const w = pct == null ? 0 : Math.round(pct * 100);
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-sm">
        <span className="font-medium text-gray-700">{label}</span>
        <span className="tabular-nums text-gray-500">{pct == null ? "—" : `${w}%`}</span>
      </div>
      <div className="h-2.5 w-full overflow-hidden rounded-full bg-gray-100">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${w}%` }} />
      </div>
      <div className="mt-1 text-sm text-gray-600">{note}</div>
    </div>
  );
}

// "Primary challenge" — separates an AWARENESS gap (the AI engines don't know the business
// yet, an information void to fill) from a NEGATIVE narrative (the AI knows it and is
// unfavorable, entrenched citations to crowd out). The former is materially faster.
export function PrimaryChallengeCard({ challenge }: { challenge: Challenge | null | undefined }) {
  if (!challenge || challenge.profile === "unknown") {
    return (
      <Card>
        <div className="text-sm font-medium text-gray-700">Primary challenge</div>
        <p className="mt-2 text-sm text-gray-500">
          {challenge?.headline ??
            "Run a completed audit to diagnose whether the main challenge is an awareness gap or an entrenched negative narrative."}
        </p>
      </Card>
    );
  }

  const st = STYLE[challenge.profile];
  const s = challenge.signals;

  return (
    <Card>
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-gray-700">Primary challenge</div>
        <div className="flex items-center gap-2">
          <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${st.speedTone}`}>
            {st.speed}
          </span>
          <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${st.badge}`}>
            {challenge.label}
          </span>
        </div>
      </div>

      <p className={`mt-3 text-base leading-relaxed ${st.accent}`}>{challenge.headline}</p>

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Track
          label="Recognition gap"
          pct={s.recognition_gap ?? s.unaware_rate}
          color="bg-indigo-500"
          note={
            s.entity_confusion_rate
              ? `AI doesn't know the business or confuses it with a same-named entity (${Math.round((s.entity_confusion_rate ?? 0) * 100)}% wrong-entity) — fill this (faster).`
              : "Answers where AI doesn't know the business — fill this (faster)."
          }
        />
        <Track
          label="Negative narrative"
          pct={s.negative_score}
          color="bg-rose-500"
          note={
            s.contested_rebutted_rate
              ? `Answers that know it and are genuinely unfavorable — crowd out (slower). ${Math.round((s.contested_rebutted_rate ?? 0) * 100)}% raise the topic but the AI rebuts it.`
              : "Answers that know it and are unfavorable — crowd out (slower)."
          }
        />
      </div>

      {challenge.by_engine && Object.keys(challenge.by_engine).length > 0 && (
        <div className="mt-4 border-t border-gray-100 pt-3">
          <div className="text-xs font-medium uppercase tracking-wide text-gray-400">
            By engine — the challenge is often different per assistant
          </div>
          <div className="mt-1 divide-y divide-gray-50">
            {Object.entries(challenge.by_engine)
              .sort((a, b) => (b[1].recognition_gap ?? 0) + (b[1].negative_score ?? 0) - (a[1].recognition_gap ?? 0) - (a[1].negative_score ?? 0))
              .map(([name, e]) => (
                <EngineRow key={name} name={name} e={e} />
              ))}
          </div>
        </div>
      )}

      <div className="mt-4 border-t border-gray-100 pt-3">
        <div className="text-xs font-medium uppercase tracking-wide text-gray-400">What this means</div>
        <p className="mt-1 text-[15px] leading-relaxed text-gray-700">{challenge.recommendation}</p>
      </div>
    </Card>
  );
}
