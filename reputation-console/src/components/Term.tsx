"use client";

import { useState } from "react";
import { glossaryLookup } from "@/lib/glossary";

// A jargon term rendered with a dotted underline and a click/hover popover explaining it
// in plain English + why it matters. Works on touch (click), unlike a native title=.
export function Term({ name, children }: { name: string; children?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const entry = glossaryLookup(name);
  const label = children ?? name;
  if (!entry) return <>{label}</>;
  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className="cursor-help border-b border-dotted border-slate-400 text-left"
        aria-label={`What is ${name}?`}
      >
        {label}
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute bottom-full left-0 z-20 mb-1 w-64 rounded-lg border border-slate-200 bg-white p-3 text-left text-xs font-normal shadow-lg"
        >
          <span className="block font-semibold text-slate-900">{name}</span>
          <span className="mt-1 block text-slate-700">{entry.plain}</span>
          <span className="mt-1 block text-slate-500">
            <span className="font-medium">Why it matters:</span> {entry.why}
          </span>
        </span>
      )}
    </span>
  );
}
