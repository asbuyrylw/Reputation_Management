"use client";

import { useState } from "react";
import { useBusiness } from "@/lib/business";
import { CreateContentModal } from "./CreateContentModal";

// Drop-in "Create content" button + its modal. Owner/editor only. Place it anywhere content lives
// (Content overview, Drafts, Media) so creating a piece is always one click away.
export function CreateContentButton({ className = "", label = "＋ Create content" }: { className?: string; label?: string }) {
  const { businessId, canEdit } = useBusiness();
  const [open, setOpen] = useState(false);
  if (!canEdit) return null;
  return (
    <>
      <button onClick={() => setOpen(true)}
        className={className || "rounded-[10px] bg-indigo px-4 py-2 text-[13px] font-semibold text-white shadow-sm hover:bg-indigo-strong"}>
        {label}
      </button>
      {open && <CreateContentModal businessId={businessId} onClose={() => setOpen(false)} />}
    </>
  );
}
