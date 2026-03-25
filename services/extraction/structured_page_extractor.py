"""Structured page extractor — pulls clean, deterministic fields from HTML.

Priority order for each field:
  mission   → meta description > og:description > JSON-LD description
  name      → JSON-LD name > og:site_name > title tag
  founded   → JSON-LD foundingDate > footer year regex
  website   → JSON-LD url > og:url > canonical link

No LLM used. All extraction is CSS/regex-based.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any


# ── Meta tag extractor ────────────────────────────────────────────────────────

class _MetaExtractor(HTMLParser):
    """Collect <meta> and <link rel=canonical> and <title> from HTML head."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.canonical: str = ""
        self.title: str = ""
        self._in_title = False
        self._title_parts: list[str] = []
        self._in_head = True
        self._json_ld_blocks: list[str] = []
        self._in_json_ld = False
        self._json_ld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "body":
            self._in_head = False
        if tag == "title":
            self._in_title = True
            return
        if tag == "meta":
            name = (attr.get("name") or attr.get("property") or "").lower().strip()
            content = attr.get("content") or ""
            if name and content:
                self.meta[name] = content
        if tag == "link":
            rel = (attr.get("rel") or "").lower().strip()
            if rel == "canonical":
                self.canonical = attr.get("href") or ""
        if tag == "script":
            stype = (attr.get("type") or "").lower().strip()
            if stype == "application/ld+json":
                self._in_json_ld = True
                self._json_ld_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._in_json_ld:
            self._json_ld_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            self.title = "".join(self._title_parts).strip()
            self._title_parts = []
        if tag == "script" and self._in_json_ld:
            self._in_json_ld = False
            raw = "".join(self._json_ld_parts).strip()
            if raw:
                self._json_ld_blocks.append(raw)
            self._json_ld_parts = []

    @property
    def json_ld_blocks(self) -> list[str]:
        return self._json_ld_blocks


def _parse_html(html: str) -> _MetaExtractor:
    parser = _MetaExtractor()
    try:
        parser.feed(html[:200_000])  # cap at 200KB — head data is near the top
        parser.close()
    except Exception:
        pass
    return parser


# ── JSON-LD helpers ───────────────────────────────────────────────────────────

def _find_schema_org_type(blocks: list[str], *types: str) -> dict[str, Any]:
    """Return the first JSON-LD block matching one of the given @type values."""
    for raw in blocks:
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and "@graph" in data:
            items = data["@graph"] if isinstance(data["@graph"], list) else [data]
        else:
            items = [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("@type") or "").lower()
            if any(t.lower() in item_type for t in types):
                return item
    return {}


# ── Public API ────────────────────────────────────────────────────────────────

def extract_structured_fields(html: str) -> dict[str, str]:
    """Return a dict of clean, deterministic fields extracted from HTML.

    Fields returned (all str, empty string when not found):
        description  — best 1-2 sentence description of the company
        name         — canonical company/product name
        founded      — founding year as string, e.g. "2017"
        url          — canonical homepage URL
        og_image     — og:image URL (useful for logo)
    """
    if not html:
        return _empty_fields()

    parser = _parse_html(html)
    meta = parser.meta

    # JSON-LD — Organization or WebSite or SoftwareApplication schema
    org = _find_schema_org_type(
        parser.json_ld_blocks,
        "Organization", "Corporation", "LocalBusiness",
        "WebSite", "SoftwareApplication",
    )

    description = _best_description(meta, org)
    name = _best_name(meta, org, parser.title)
    founded = _best_founded(org)
    url = _best_url(meta, org, parser.canonical)

    return {
        "description": description,
        "name": name,
        "founded": founded,
        "url": url,
        "og_image": meta.get("og:image", ""),
    }


def extract_meta_description(html: str) -> str:
    """Return the best short description from HTML meta/OG tags. No LLM."""
    return extract_structured_fields(html).get("description", "")


def _empty_fields() -> dict[str, str]:
    return {"description": "", "name": "", "founded": "", "url": "", "og_image": ""}


def _best_description(meta: dict[str, str], org: dict[str, Any]) -> str:
    """Priority: meta description > og:description > JSON-LD description."""
    candidates = [
        meta.get("description", ""),
        meta.get("og:description", ""),
        meta.get("twitter:description", ""),
        str(org.get("description") or ""),
    ]
    for c in candidates:
        cleaned = _clean_short_text(c)
        if cleaned and len(cleaned) > 20:
            return cleaned[:300]
    return ""


def _best_name(meta: dict[str, str], org: dict[str, Any], title: str) -> str:
    """Priority: og:site_name > JSON-LD name > title tag (first segment)."""
    candidates = [
        meta.get("og:site_name", ""),
        meta.get("application-name", ""),
        str(org.get("name") or ""),
    ]
    for c in candidates:
        cleaned = _clean_short_text(c)
        if cleaned and 2 <= len(cleaned) <= 60:
            return cleaned
    # Fall back to first segment of title tag
    if title:
        for sep in (" | ", " - ", " – ", " — ", ": ", " · "):
            if sep in title:
                segment = title.split(sep)[0].strip()
                if 2 <= len(segment) <= 60:
                    return segment
        if len(title) <= 60:
            return title.strip()
    return ""


def _best_founded(org: dict[str, Any]) -> str:
    """Extract founding year from JSON-LD foundingDate."""
    raw = str(org.get("foundingDate") or org.get("founded") or "")
    match = re.search(r"\b(19|20)\d{2}\b", raw)
    if match:
        return match.group(0)
    return ""


def _best_url(meta: dict[str, str], org: dict[str, Any], canonical: str) -> str:
    candidates = [
        canonical,
        meta.get("og:url", ""),
        str(org.get("url") or ""),
    ]
    for c in candidates:
        c = c.strip()
        if c.startswith("http"):
            return c
    return ""


def _clean_short_text(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip()
    # Reject if it looks like JavaScript or HTML
    if any(bad in text for bad in ("<script", "function(", "document.", "window.", "{\"@")):
        return ""
    return text
