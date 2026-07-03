"use client";

import { useState } from "react";

// Multi-value keyword input (LinkedIn-style). Stores/returns a comma-joined string so it stays
// compatible with the engine (which splits services on commas and uses the first as the primary
// category query), but presents as removable chips. Type a value and press Enter or comma to add.
export function TagInput({
  value,
  onChange,
  placeholder,
  className = "",
}: {
  value: string;
  onChange: (commaJoined: string) => void;
  placeholder?: string;
  className?: string;
}) {
  const [draft, setDraft] = useState("");
  const tags = value.split(",").map((t) => t.trim()).filter(Boolean);

  const commit = (raw: string) => {
    const next = raw.trim().replace(/,+$/, "").trim();
    if (!next) return;
    if (!tags.some((t) => t.toLowerCase() === next.toLowerCase())) {
      onChange([...tags, next].join(", "));
    }
    setDraft("");
  };
  const removeAt = (i: number) => onChange(tags.filter((_, j) => j !== i).join(", "));

  return (
    <div className={`flex flex-wrap items-center gap-1.5 rounded-md border border-slate-300 px-2 py-1.5 ${className}`}>
      {tags.map((t, i) => (
        <span key={`${t}-${i}`} className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700">
          {t}
          <button type="button" onClick={() => removeAt(i)} className="text-indigo-400 hover:text-indigo-700" aria-label={`remove ${t}`}>
            ×
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => {
          const v = e.target.value;
          if (v.includes(",")) commit(v); // typing/pasting a comma commits the tag
          else setDraft(v);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit(draft);
          } else if (e.key === "Backspace" && !draft && tags.length) {
            removeAt(tags.length - 1);
          }
        }}
        onBlur={() => draft && commit(draft)}
        placeholder={tags.length ? "" : placeholder}
        className="min-w-[8rem] flex-1 border-0 bg-transparent px-1 py-0.5 text-sm outline-none"
      />
    </div>
  );
}
