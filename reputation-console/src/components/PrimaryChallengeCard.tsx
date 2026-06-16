"use client";

import type { Challenge, ChallengeProfile } from "@/lib/types";
import { Card } from "./ui";

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
      <div className="mt-1 text-xs text-gray-400">{note}</div>
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

      <p className={`mt-3 text-sm leading-relaxed ${st.accent}`}>{challenge.headline}</p>

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Track
          label="Awareness void"
          pct={s.unaware_rate}
          color="bg-indigo-500"
          note="Answers where AI doesn't know the business — fill this (faster)."
        />
        <Track
          label="Negative narrative"
          pct={s.negative_score}
          color="bg-rose-500"
          note="Answers that know it and are unfavorable — crowd out (slower)."
        />
      </div>

      <div className="mt-4 border-t border-gray-100 pt-3">
        <div className="text-xs font-medium uppercase tracking-wide text-gray-400">What this means</div>
        <p className="mt-1 text-sm text-gray-600">{challenge.recommendation}</p>
      </div>
    </Card>
  );
}
