"""Helpers for extracting readable text from vendor HTML pages."""

from __future__ import annotations

import html
from html.parser import HTMLParser
import re

SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "nav",
    "footer",
    "aside",
    "form",
    "iframe",
    "template",
    "head",
}

NOISE_HINTS = (
    "analytics",
    "banner",
    "breadcrumb",
    "consent",
    "cookie",
    "footer",
    "menu",
    "modal",
    "nav",
    "newsletter",
    "popup",
    "promotion",
    "search",
    "share",
    "sidebar",
    "social",
    "subscribe",
    "tracking",
)

BLOCK_TAGS = {
    "article",
    "br",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "main",
    "p",
    "section",
    "tr",
}

VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class _VisibleTextParser(HTMLParser):
    """Collect visible text while skipping noisy sections."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._skip_depth = 0
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if self._skip_depth > 0:
            if normalized_tag not in VOID_TAGS:
                self._skip_depth += 1
            return

        if self._should_skip(normalized_tag, attrs):
            self._skip_depth = 1
            return

        if normalized_tag in BLOCK_TAGS:
            self._text_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if self._skip_depth > 0:
            self._skip_depth -= 1
            return

        if normalized_tag in BLOCK_TAGS:
            self._text_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return

        cleaned = data.strip()
        if cleaned:
            self._text_parts.append(cleaned)
            self._text_parts.append(" ")

    def get_text(self) -> str:
        combined_text = html.unescape("".join(self._text_parts))
        return re.sub(r"\s+", " ", combined_text).strip()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth > 0 or self._should_skip(tag.lower(), attrs):
            return
        if tag.lower() in BLOCK_TAGS:
            self._text_parts.append(" ")

    def _should_skip(self, tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        if tag in SKIP_TAGS:
            return True

        attr_values = " ".join(
            value.lower()
            for name, value in attrs
            if name.lower() in {"class", "id", "role", "aria-label"} and value
        )
        if not attr_values:
            return False

        return any(noise_hint in attr_values for noise_hint in NOISE_HINTS)


def extract_visible_text(html_content: str, *, max_chars: int | None = None) -> str:
    """Return cleaned visible text from HTML for deterministic extraction."""
    if not html_content:
        return ""

    parser = _VisibleTextParser()
    parser.feed(html_content)
    parser.close()
    extracted_text = parser.get_text()
    if max_chars is None or max_chars <= 0:
        return extracted_text
    return extracted_text[:max_chars].strip()
