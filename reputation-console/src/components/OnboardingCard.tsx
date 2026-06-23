"use client";

import Link from "next/link";
import { Card } from "./ui";
import { useOnboarding } from "@/lib/hooks";

// Getting-started checklist: guides a new owner from an empty account to a running program.
// Hides into a one-line confirmation once every step is done.
export default function OnboardingCard({ businessId }: { businessId: number | null }) {
  const { data } = useOnboarding(businessId);
  if (!data) return null;

  if (data.complete) {
    return (
      <Card className="border-emerald-200 bg-emerald-50/50">
        <p className="text-sm text-emerald-800">
          ✓ Setup complete — all {data.total} getting-started steps done.
        </p>
      </Card>
    );
  }

  return (
    <Card className="border-indigo-200 bg-indigo-50/40">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">Getting started</h3>
        <span className="text-xs text-slate-500">{data.done} of {data.total} done</span>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-indigo-100">
        <div className="h-full rounded-full bg-indigo-500" style={{ width: `${(data.done / data.total) * 100}%` }} />
      </div>
      <ul className="mt-3 space-y-1.5">
        {data.steps.map((s) => (
          <li key={s.key} className="flex items-center justify-between gap-3 text-sm">
            <span className={s.done ? "text-slate-400 line-through" : "text-slate-800"}>
              <span className="mr-1.5">{s.done ? "✓" : "○"}</span>{s.label}
            </span>
            {!s.done && (
              <Link href={s.href} className="shrink-0 text-xs font-medium text-indigo-600 hover:underline">
                Do this →
              </Link>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
