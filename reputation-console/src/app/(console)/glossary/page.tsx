"use client";

import { Card, PageHeader } from "@/components/ui";
import { GLOSSARY } from "@/lib/glossary";

// A plain-English reference for every term used across the console.
export default function GlossaryPage() {
  const terms = Object.entries(GLOSSARY).sort((a, b) => a[0].localeCompare(b[0]));
  return (
    <div>
      <PageHeader
        title="Glossary"
        subtitle="Every term in plain English — what it means and why it matters to you."
      />
      <div className="space-y-3">
        {terms.map(([term, e]) => (
          <Card key={term}>
            <div className="text-sm font-semibold capitalize text-gray-900">{term}</div>
            <p className="mt-1 text-sm text-gray-700">{e.plain}</p>
            <p className="mt-1 text-sm text-gray-500"><span className="font-medium">Why it matters:</span> {e.why}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}
