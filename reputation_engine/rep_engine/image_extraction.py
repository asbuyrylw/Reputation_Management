"""Extract the inline image markers the content writer embeds as ``![alt](IMAGE: prompt)`` (see
GEN_SYSTEM in content_generator) into structured metadata: the SEO alt text, the generation
prompt, and the section the image illustrates. Deterministic + keyless. Phase 4 (visual content)
consumes this to produce a hero/section image per marker with ready-made, descriptive alt text.
"""
from __future__ import annotations

import re

# ![alt text](IMAGE: a short generation prompt)
_MARKER = re.compile(r"!\[([^\]]*)\]\(\s*IMAGE:\s*([^)]*)\)", re.I)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.M)


def extract_image_markers(body: str) -> list[dict]:
    """Return one dict per image marker: {index, alt_text, prompt, section_heading, position}.
    section_heading is the nearest preceding markdown heading (the section the image belongs to)."""
    body = body or ""
    heads = [(m.start(), (m.group(1) or "").strip()) for m in _HEADING.finditer(body)]
    out: list[dict] = []
    for i, m in enumerate(_MARKER.finditer(body)):
        alt = (m.group(1) or "").strip()
        prompt = (m.group(2) or "").strip()
        section = ""
        for pos, txt in heads:
            if pos < m.start():
                section = txt
            else:
                break
        out.append({"index": i, "alt_text": alt, "prompt": prompt,
                    "section_heading": section, "position": m.start()})
    return out


def image_count(body: str) -> int:
    return len(_MARKER.findall(body or ""))
