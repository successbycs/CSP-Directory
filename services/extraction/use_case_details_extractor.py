"""Deterministic use-case-details extraction from explored vendor pages (M67).

Derives {label, url, summary} records from product/solution sub-pages discovered
during site exploration. No LLM required — uses URL path structure and first-line
heuristics only.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

# Path segments that indicate a use-case / solution / feature parent directory
_USE_CASE_PARENT_SEGMENTS = frozenset(
    [
        "use-case",
        "use-cases",
        "use_case",
        "use_cases",
        "usecases",
        "solution",
        "solutions",
        "feature",
        "features",
        "how-we-help",
        "how-it-works",
        "product",
        "platform",
        "capability",
        "capabilities",
        "module",
        "modules",
    ]
)

_MIN_LABEL_CHARS = 3
_SUMMARY_MAX_CHARS = 200
_MIN_LINE_CHARS = 20  # Skip nav/header lines shorter than this


def extract_use_case_details(explored_pages: dict[str, Any]) -> list[dict[str, str]]:
    """Return [{label, url, summary}] for product/solution sub-pages in explored_pages.

    Only includes pages whose URL path identifies a specific use case or product
    feature (i.e. the URL has a recognised parent segment followed by a slug).
    Top-level pages like /solutions or /product are excluded.

    Deduplicates by lowercased label.
    """
    results: list[dict[str, str]] = []
    seen_labels: set[str] = set()

    for _page_key, page_value in explored_pages.items():
        if not isinstance(page_value, dict):
            continue
        url = str(page_value.get("website") or page_value.get("url") or "").strip()
        text = str(page_value.get("text") or "").strip()
        if not url or not text:
            continue

        label = _label_from_url(url)
        if not label:
            continue

        label_lower = label.lower()
        if label_lower in seen_labels:
            continue

        summary = _first_meaningful_line(text)
        results.append({"label": label, "url": url, "summary": summary})
        seen_labels.add(label_lower)

    return results


def _label_from_url(url: str) -> str:
    """Derive a human-readable label from a URL, or empty string if not a use-case page.

    Looks for a known parent segment in the URL path followed by a non-empty slug.
    E.g. /solutions/onboarding → "Onboarding", /features/health-scores → "Health Scores".
    Top-level pages (/solutions, /product) return "".
    """
    try:
        path = urlparse(url).path.rstrip("/")
    except Exception:
        return ""

    segments = [s for s in path.split("/") if s]
    if len(segments) < 2:
        return ""  # top-level page, not a specific use case

    for i, seg in enumerate(segments):
        if seg.lower() in _USE_CASE_PARENT_SEGMENTS and i + 1 < len(segments):
            slug = segments[i + 1]
            return _slug_to_title(slug)

    return ""


def _slug_to_title(slug: str) -> str:
    """Convert a URL slug to a title-cased label string."""
    cleaned = re.sub(r"[-_]", " ", slug)
    cleaned = re.sub(r"[^a-zA-Z0-9 ]", "", cleaned).strip()
    if not cleaned or len(cleaned) < _MIN_LABEL_CHARS:
        return ""
    return cleaned.title()


def _first_meaningful_line(text: str, max_chars: int = _SUMMARY_MAX_CHARS) -> str:
    """Return the first line with >= _MIN_LINE_CHARS characters, truncated to max_chars."""
    for line in text.split("\n"):
        stripped = line.strip()
        if len(stripped) >= _MIN_LINE_CHARS:
            return stripped[:max_chars]
    return text.strip()[:max_chars]
