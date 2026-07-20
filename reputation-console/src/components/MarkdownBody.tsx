"use client";

import type { ReactNode } from "react";

// Minimal, dependency-free markdown renderer for generated article bodies: headings, bullet &
// numbered lists, bold/italic/code/links, and paragraphs. NOT a full CommonMark parser — just the
// constructs our content generator emits — so a draft reads like an article instead of raw
// "## Heading" / "- bullet" text.
function inline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|_[^_\s][^_]*_|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("**")) nodes.push(<strong key={k++} className="font-semibold text-ink">{t.slice(2, -2)}</strong>);
    else if (t.startsWith("`")) nodes.push(<code key={k++} className="rounded bg-line/60 px-1 py-0.5 text-[0.85em]">{t.slice(1, -1)}</code>);
    else if (t.startsWith("[")) {
      const mm = /\[([^\]]+)\]\(([^)]+)\)/.exec(t);
      nodes.push(mm ? <a key={k++} href={mm[2]} target="_blank" rel="noreferrer" className="text-indigo underline">{mm[1]}</a> : t);
    } else nodes.push(<em key={k++}>{t.slice(1, -1)}</em>);
    last = m.index + t.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

const STRUCT = /^(#{1,4}\s|\s*[-*+]\s|\s*\d+[.)]\s)/;

export function MarkdownBody({ text, className }: { text: string; className?: string }) {
  const lines = (text || "").replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }

    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      const lvl = h[1].length;
      const cls = lvl <= 1
        ? "mt-4 text-[17px] font-semibold leading-snug text-ink"
        : lvl === 2 ? "mt-4 text-[15.5px] font-semibold leading-snug text-ink" : "mt-3 text-[14px] font-semibold text-ink-2";
      blocks.push(<div key={key++} className={cls}>{inline(h[2])}</div>);
      i++; continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        items.push(<li key={items.length}>{inline(lines[i].replace(/^\s*[-*+]\s+/, ""))}</li>);
        i++;
      }
      blocks.push(<ul key={key++} className="mt-1.5 list-disc space-y-1 pl-5">{items}</ul>);
      continue;
    }

    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        items.push(<li key={items.length}>{inline(lines[i].replace(/^\s*\d+[.)]\s+/, ""))}</li>);
        i++;
      }
      blocks.push(<ol key={key++} className="mt-1.5 list-decimal space-y-1 pl-5">{items}</ol>);
      continue;
    }

    // paragraph — join consecutive non-blank, non-structural lines
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !STRUCT.test(lines[i])) {
      para.push(lines[i]);
      i++;
    }
    blocks.push(<p key={key++} className="mt-2 leading-relaxed">{inline(para.join(" "))}</p>);
  }
  return <div className={className}>{blocks}</div>;
}
