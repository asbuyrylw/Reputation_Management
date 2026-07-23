"""
Markdown -> clean HTML for publishing (channel formatting).
===========================================================
Generated drafts are Markdown. The WordPress REST API's `content` field expects HTML, so posting the
raw Markdown made `##`, `**`, `[text](url)`, `![alt](url)`, tables, and lists render as literal text
on the blog/site. This converts a draft body to clean, professional HTML before publish.

Primary path uses the `markdown` package (tables, fenced code, sane lists). If it isn't installed yet
(e.g. a build hasn't picked up the new dependency), a dependency-free fallback handles the blocks our
generator actually produces (headings, paragraphs, bold/italic, links, images, ordered/unordered
lists, blockquotes, pipe tables, horizontal rules, inline code) so publishing never ships raw
Markdown. Pure + fail-safe: any error returns the input wrapped in a paragraph, never raises.
"""
from __future__ import annotations

import html
import re
from typing import Optional


def to_html(md: Optional[str]) -> str:
    """Convert a Markdown draft body to HTML. Fail-safe: never raises."""
    text = (md or "").strip()
    if not text:
        return ""
    try:
        import markdown as _md  # type: ignore
        return _md.markdown(text, extensions=["extra", "sane_lists"], output_format="html5")
    except Exception:  # noqa: BLE001 -- package missing or a conversion error -> lightweight fallback
        try:
            return _fallback(text)
        except Exception:  # noqa: BLE001 -- absolute last resort: never ship raw markdown blindly
            return "<p>" + html.escape(text).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"


_IMG = re.compile(r"!\[([^\]]*)\]\(\s*([^)\s]+)[^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\(\s*([^)\s]+)[^)]*\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\w)")
_CODE = re.compile(r"`([^`]+)`")
_H = re.compile(r"^(#{1,6})\s+(.*)$")


def _inline(s: str) -> str:
    """Escape text ONCE (& < >), then apply inline Markdown -> HTML. URLs/text captured after the
    escape are already safe, so the replacements embed them directly (no double-escaping)."""
    s = html.escape(s, quote=False)
    s = _IMG.sub(lambda m: f'<img src="{m.group(2)}" alt="{m.group(1)}" loading="lazy" />', s)
    s = _LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', s)
    s = _CODE.sub(lambda m: f"<code>{m.group(1)}</code>", s)
    s = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", s)
    s = _ITALIC.sub(lambda m: f"<em>{m.group(1)}</em>", s)
    return s


def _table(rows: list[str]) -> str:
    """A GitHub-style pipe table: header row, a --- separator, then body rows."""
    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]
    head = cells(rows[0])
    body = [cells(r) for r in rows[2:]]
    out = ["<table><thead><tr>"]
    out += [f"<th>{_inline(c)}</th>" for c in head]
    out.append("</tr></thead><tbody>")
    for r in body:
        out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _is_table_sep(line: str) -> bool:
    return bool(re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", line)) and "-" in line


def _fallback(md: str) -> str:
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    para: list[str] = []

    def flush_para() -> None:
        if para:
            out.append("<p>" + _inline(" ".join(para).strip()) + "</p>")
            para.clear()

    while i < n:
        line = lines[i]
        stripped = line.strip()
        # blank -> paragraph break
        if not stripped:
            flush_para(); i += 1; continue
        # heading
        mh = _H.match(stripped)
        if mh:
            flush_para()
            lvl = len(mh.group(1))
            out.append(f"<h{lvl}>{_inline(mh.group(2).strip())}</h{lvl}>")
            i += 1; continue
        # horizontal rule
        if re.match(r"^(\*{3,}|-{3,}|_{3,})$", stripped):
            flush_para(); out.append("<hr />"); i += 1; continue
        # pipe table (header + separator + rows)
        if "|" in stripped and i + 1 < n and _is_table_sep(lines[i + 1]):
            flush_para()
            tbl = [lines[i], lines[i + 1]]
            j = i + 2
            while j < n and "|" in lines[j].strip() and lines[j].strip():
                tbl.append(lines[j]); j += 1
            out.append(_table(tbl)); i = j; continue
        # blockquote
        if stripped.startswith(">"):
            flush_para()
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i])); i += 1
            out.append("<blockquote>" + _inline(" ".join(quote).strip()) + "</blockquote>")
            continue
        # unordered / ordered list
        if re.match(r"^\s*([-*+]|\d+\.)\s+", line):
            flush_para()
            ordered = bool(re.match(r"^\s*\d+\.\s+", line))
            tag = "ol" if ordered else "ul"
            items = []
            while i < n and re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i]):
                items.append(re.sub(r"^\s*([-*+]|\d+\.)\s+", "", lines[i])); i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(it.strip())}</li>" for it in items) + f"</{tag}>")
            continue
        # standalone image line
        if _IMG.fullmatch(stripped):
            flush_para(); out.append(_inline(stripped)); i += 1; continue
        # paragraph text (accumulate)
        para.append(stripped); i += 1

    flush_para()
    return "\n".join(out)
