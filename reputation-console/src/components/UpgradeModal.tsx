"use client";

import Link from "next/link";

// Shown when an action hits a billing wall (402/429). Turns the dead-end error at the moment
// of highest intent into a path to /billing. The message comes straight from the API (it names
// the plan + cap), so we just frame it and link to the plans page.
export function UpgradeModal({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-bold text-slate-900">You’ve hit your plan’s limit</h3>
        <p className="mt-2 text-sm text-slate-600">{message || "Upgrade your plan to keep going."}</p>
        <div className="mt-4 flex items-center justify-end gap-2">
          <button onClick={onClose} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100">
            Not now
          </button>
          <Link
            href="/billing"
            onClick={onClose}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            View plans
          </Link>
        </div>
      </div>
    </div>
  );
}
