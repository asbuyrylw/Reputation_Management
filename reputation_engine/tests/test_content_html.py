"""Markdown -> HTML publishing conversion (channel formatting) — regression lock.

Proves a draft's Markdown becomes clean HTML so WordPress doesn't render raw ##/**/![]() as literal
text. Tests the dependency-free fallback directly (so it passes with or without the `markdown` pkg),
plus to_html's contract (no raw block markers, fail-safe on empty).
"""
from __future__ import annotations

from rep_engine import content_html as ch


def test_headings_and_paragraphs():
    h = ch._fallback("# Title\n\nA paragraph here.\n\n## Section\nMore text.")
    assert "<h1>Title</h1>" in h and "<h2>Section</h2>" in h
    assert "<p>A paragraph here.</p>" in h


def test_bold_link_image():
    h = ch._fallback("This is **bold** and a [link](https://x.com) and ![alt text](https://x/img.png).")
    assert "<strong>bold</strong>" in h
    assert '<a href="https://x.com">link</a>' in h
    assert '<img src="https://x/img.png" alt="alt text"' in h


def test_lists():
    assert ch._fallback("- one\n- two\n- three").count("<li>") == 3
    assert "<ul>" in ch._fallback("- one\n- two")
    ol = ch._fallback("1. first\n2. second")
    assert "<ol>" in ol and ol.count("<li>") == 2


def test_pipe_table():
    h = ch._fallback("| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |")
    assert "<table>" in h and "<th>A</th>" in h and "<td>1</td>" in h and "<td>4</td>" in h


def test_faq_headings():
    h = ch._fallback("### What is term life?\nCoverage for a set term.\n\n### How much?\nDepends.")
    assert "<h3>What is term life?</h3>" in h


def test_ampersand_escaped_url_not_double_escaped():
    h = ch._fallback("See [our page](https://x.com?a=1&b=2) and Tom & Jerry.")
    assert "Tom &amp; Jerry" in h                       # text & escaped
    assert "a=1&amp;b=2" in h and "&amp;amp;" not in h  # URL escaped once, not twice


def test_to_html_no_raw_block_markers():
    h = ch.to_html("## Heading\n\nSome **text** with a [link](https://x.com).")
    assert "## Heading" not in h and "**text**" not in h
    assert "<a href=" in h


def test_empty_is_safe():
    assert ch.to_html("") == "" and ch.to_html(None) == ""
