"""Website exploration helpers for discovering high-signal vendor pages."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

from services.config.load_config import EnrichmentConfig, load_pipeline_config
from services.extraction.identity import normalize_domain
from services.extraction.page_text_extractor import extract_visible_text
from services.enrichment import discovery_mode
from services.enrichment.vendor_fetcher import _should_skip_page

logger = logging.getLogger(__name__)

PagePayload = dict[str, str | int]
ExploredPages = dict[str, object]


@dataclass(frozen=True)
class _LinkCandidate:
    page_key: str
    url: str
    score: int


def explore_vendor_site(homepage_payload: PagePayload) -> ExploredPages:
    """Return a bounded recursive page bundle for downstream extraction."""
    config = load_pipeline_config().enrichment
    homepage_html = str(homepage_payload.get("html", ""))
    homepage_url = str(homepage_payload.get("website", ""))
    homepage_url = _normalize_page_url(homepage_url)

    if not homepage_url:
        return {
            "homepage": homepage_payload,
            "extra_pages": [],
        }

    initial_candidates = _select_page_candidates(homepage_url, homepage_html, config)
    initial_candidates.extend(_build_discovery_mode_candidates(homepage_payload, config))
    initial_candidates.extend(_build_seed_candidates(homepage_url, config))
    pending_candidates: deque[tuple[_LinkCandidate, int]] = deque(
        (candidate, 1) for candidate in _dedupe_candidates(initial_candidates)
    )
    queued_urls = {candidate.url for candidate, _depth in pending_candidates}
    fetched_urls = {homepage_url}
    named_pages: dict[str, PagePayload] = {}
    extra_pages: list[PagePayload] = []
    fetched_count = 0

    while pending_candidates and fetched_count < config.max_pages_total:
        candidate, depth = pending_candidates.popleft()
        queued_urls.discard(candidate.url)
        if candidate.url in fetched_urls:
            continue

        page_payload = _fetch_page(candidate.url, candidate.page_key, config)
        fetched_urls.add(candidate.url)
        if int(page_payload["status_code"]) == 0 or int(page_payload["status_code"]) >= 400:
            continue

        fetched_count += 1
        _store_page_payload(candidate, page_payload, named_pages=named_pages, extra_pages=extra_pages)

        if depth >= config.max_crawl_depth:
            continue

        child_html = str(page_payload.get("html", ""))
        child_url = str(page_payload.get("website") or page_payload.get("url") or "").strip()
        if not child_html or not child_url:
            continue

        for child_candidate in _select_page_candidates(child_url, child_html, config):
            if child_candidate.url in fetched_urls or child_candidate.url in queued_urls or child_candidate.url == homepage_url:
                continue
            pending_candidates.append((child_candidate, depth + 1))
            queued_urls.add(child_candidate.url)

    return _assemble_explored_pages(
        homepage_payload=homepage_payload,
        extra_pages=extra_pages,
        named_pages=named_pages,
        page_priority=config.page_priority,
    )


def _select_page_candidates(
    homepage_url: str,
    homepage_html: str,
    config: EnrichmentConfig,
) -> list[_LinkCandidate]:
    """Return ranked same-domain page candidates."""
    homepage_domain = _normalized_domain(homepage_url)
    link_parser = _LinkParser()
    link_parser.feed(homepage_html)
    link_parser.close()

    best_named_candidates: dict[str, _LinkCandidate] = {}
    extra_candidates: dict[str, _LinkCandidate] = {}

    for href, anchor_text in link_parser.links:
        normalized_url = _normalize_page_url(urljoin(homepage_url, href))
        if not normalized_url or not _is_allowed_site(normalized_url, homepage_domain, config):
            continue
        if normalized_url == _normalize_page_url(homepage_url):
            continue

        candidate = _build_candidate(normalized_url, anchor_text, config)
        if candidate is None:
            continue

        if candidate.page_key == "extra_page":
            previous_candidate = extra_candidates.get(candidate.url)
            if previous_candidate is None or candidate.score > previous_candidate.score:
                extra_candidates[candidate.url] = candidate
            continue

        previous_candidate = best_named_candidates.get(candidate.page_key)
        if previous_candidate is None or candidate.score > previous_candidate.score:
            best_named_candidates[candidate.page_key] = candidate

    ranked_named_candidates = [
        best_named_candidates[page_key]
        for page_key in config.page_priority
        if page_key in best_named_candidates
    ]
    ranked_extra_candidates = sorted(
        extra_candidates.values(),
        key=lambda candidate: candidate.score,
        reverse=True,
    )
    return ranked_named_candidates + ranked_extra_candidates


def _build_candidate(
    url: str,
    anchor_text: str,
    config: EnrichmentConfig,
) -> _LinkCandidate | None:
    """Classify and score one internal link."""
    lowered_url = url.lower()
    lowered_anchor_text = anchor_text.lower()
    combined_text = f"{lowered_url} {lowered_anchor_text}".strip()
    if not combined_text:
        return None

    if _looks_like_blocklisted_page(combined_text, config):
        return None

    is_junk = _looks_like_junk_page(combined_text, config)
    page_patterns = config.page_patterns
    matched_page_keys = [
        page_key
        for page_key, patterns in page_patterns.items()
        if any(pattern in lowered_url or pattern in lowered_anchor_text for pattern in patterns)
    ]

    if not matched_page_keys and is_junk:
        return None

    if matched_page_keys:
        page_key = min(
            matched_page_keys,
            key=lambda candidate_key: config.page_priority.index(candidate_key)
            if candidate_key in config.page_priority
            else len(config.page_priority),
        )
        score = _candidate_score(page_key, lowered_url, lowered_anchor_text, is_junk, config)
        return _LinkCandidate(page_key=page_key, url=url, score=score)

    if _looks_like_product_slug(url, lowered_anchor_text):
        score = _candidate_score("product_page", lowered_url, lowered_anchor_text, is_junk, config)
        return _LinkCandidate(page_key="product_page", url=url, score=score)

    if _looks_like_high_value_extra(combined_text):
        score = _candidate_score("extra_page", lowered_url, lowered_anchor_text, is_junk, config)
        return _LinkCandidate(page_key="extra_page", url=url, score=score)

    return None


def _candidate_score(
    page_key: str,
    lowered_url: str,
    lowered_anchor_text: str,
    is_junk: bool,
    config: EnrichmentConfig,
) -> int:
    """Return a simple deterministic score for candidate selection."""
    priority_bonus = 0
    if page_key in config.page_priority:
        priority_bonus = (len(config.page_priority) - config.page_priority.index(page_key)) * 10

    path = urlparse(lowered_url).path
    path_parts = [segment for segment in path.split("/") if segment]
    direct_path_bonus = max(0, 4 - len(path_parts))

    match_bonus = 0
    for pattern in config.page_patterns.get(page_key, ()):
        if pattern in lowered_url:
            match_bonus += 4
        if pattern in lowered_anchor_text:
            match_bonus += 3

    if page_key == "extra_page":
        match_bonus += 5

    junk_penalty = 20 if is_junk else 0
    query_penalty = 2 if "?" in lowered_url else 0
    return priority_bonus + direct_path_bonus + match_bonus - junk_penalty - query_penalty


def _looks_like_junk_page(text: str, config: EnrichmentConfig) -> bool:
    """Return True when a page looks operational, legal, or low-value."""
    return any(hint in text for hint in config.junk_hints)


def _looks_like_blocklisted_page(text: str, config: EnrichmentConfig) -> bool:
    """Return True when a page should never be crawled."""
    return any(hint in text for hint in config.blocklist_hints)


def _looks_like_high_value_extra(text: str) -> bool:
    """Return True when a page looks useful but does not map to a primary slot."""
    return any(
        hint in text
        for hint in (
            "ai",
            "article",
            "automation",
            "blog",
            "case study",
            "customer success",
            "contact",
            "demo",
            "help",
            "feature",
            "platform",
            "review",
            "solution",
            "testimonial",
            "use case",
        )
    )


def _looks_like_product_slug(url: str, lowered_anchor_text: str) -> bool:
    """Return True for short direct-child product slugs like /staircase-ai."""
    parsed = urlparse(url)
    path_parts = [segment for segment in parsed.path.lower().split("/") if segment]
    if not path_parts or len(path_parts) > 2:
        return False

    slug = path_parts[-1]
    if len(slug) < 3:
        return False
    if any(character.isdigit() for character in slug):
        return False
    if slug in {
        "about",
        "about-us",
        "blog",
        "careers",
        "case-studies",
        "contact",
        "contact-us",
        "customers",
        "demo",
        "docs",
        "documentation",
        "help",
        "integrations",
        "legal",
        "login",
        "news",
        "platform",
        "pricing",
        "privacy",
        "resources",
        "security",
        "signin",
        "support",
        "team",
        "terms",
        "testimonials",
        "trust",
    }:
        return False
    if "." in slug:
        return False

    if lowered_anchor_text:
        word_count = len([part for part in lowered_anchor_text.split() if part])
        if 0 < word_count <= 5:
            return True
    return "-" in slug or len(path_parts) == 1


def _fetch_page(url: str, page_type: str, config: EnrichmentConfig) -> PagePayload:
    """Fetch a discovered page and return extracted text."""
    try:
        response = requests.get(url, timeout=config.request_timeout_seconds)
    except Exception as error:
        logger.warning("Skipping unreachable %s at %s: %s", page_type, url, error)
        fallback_payload = discovery_mode.fetch_page_with_fallback(url, config=config)
        if fallback_payload:
            normalized_url = _normalize_page_url(url)
            html = str(fallback_payload.get("html", ""))
            text = str(fallback_payload.get("text", "")) or extract_visible_text(html)
            return {
                "vendor_name": "",
                "website": normalized_url,
                "url": normalized_url,
                "page_type": page_type,
                "status_code": int(fallback_payload.get("status_code", 200)),
                "html": html,
                "text": text,
                "fetch_backend": str(fallback_payload.get("fetch_backend", "fallback")),
            }
        return _empty_page_payload(url, page_type, status_code=0)

    if _should_skip_page(response.status_code, response.text):
        logger.info("Skipping blocked or invalid %s at %s", page_type, url)
        fallback_payload = discovery_mode.fetch_page_with_fallback(url, config=config)
        if fallback_payload:
            normalized_url = _normalize_page_url(url)
            html = str(fallback_payload.get("html", ""))
            text = str(fallback_payload.get("text", "")) or extract_visible_text(html)
            return {
                "vendor_name": "",
                "website": normalized_url,
                "url": normalized_url,
                "page_type": page_type,
                "status_code": int(fallback_payload.get("status_code", response.status_code)),
                "html": html,
                "text": text,
                "fetch_backend": str(fallback_payload.get("fetch_backend", "fallback")),
            }
        return _empty_page_payload(_normalize_page_url(url), page_type, status_code=response.status_code)

    normalized_url = _normalize_page_url(url)
    return {
        "vendor_name": "",
        "website": normalized_url,
        "url": normalized_url,
        "page_type": page_type,
        "status_code": response.status_code,
        "html": response.text,
        "text": extract_visible_text(response.text),
        "fetch_backend": "requests",
    }


def _build_seed_candidates(homepage_url: str, config: EnrichmentConfig) -> list[_LinkCandidate]:
    """Return deterministic fallback candidates for blocked or sparse sites."""
    candidates: list[_LinkCandidate] = []
    for seed_path in config.seed_paths:
        seeded_url = _normalize_page_url(urljoin(homepage_url, seed_path))
        if not seeded_url:
            continue
        candidate = _build_candidate(seeded_url, seed_path, config)
        if candidate is not None:
            candidates.append(candidate)

    base_host = urlparse(homepage_url).hostname or ""
    site_key = _site_key(base_host)
    scheme = urlparse(homepage_url).scheme or "https"
    if not site_key:
        return candidates

    for subdomain in config.trusted_subdomains:
        seeded_url = _normalize_page_url(f"{scheme}://{subdomain}.{site_key}/")
        if not seeded_url:
            continue
        candidate = _build_candidate(seeded_url, subdomain, config)
        if candidate is None:
            if subdomain == "docs":
                candidate = _LinkCandidate(page_key="developer_docs_page", url=seeded_url, score=95)
            elif subdomain == "blog":
                candidate = _LinkCandidate(page_key="blog_page", url=seeded_url, score=90)
            elif subdomain in {"help", "support"}:
                candidate = _LinkCandidate(page_key="help_page", url=seeded_url, score=85)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _build_discovery_mode_candidates(
    homepage_payload: PagePayload,
    config: EnrichmentConfig,
) -> list[_LinkCandidate]:
    homepage_url = _normalize_page_url(str(homepage_payload.get("website", "")))
    if not homepage_url:
        return []

    candidates: list[_LinkCandidate] = []
    for discovered_url, anchor_text in discovery_mode.discover_vendor_links(homepage_payload, config):
        normalized_url = _normalize_page_url(discovered_url)
        if not normalized_url or normalized_url == homepage_url:
            continue
        candidate = _build_candidate(normalized_url, anchor_text, config)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _dedupe_candidates(candidates: list[_LinkCandidate]) -> list[_LinkCandidate]:
    deduped: list[_LinkCandidate] = []
    seen_urls: set[str] = set()
    for candidate in candidates:
        if candidate.url in seen_urls:
            continue
        deduped.append(candidate)
        seen_urls.add(candidate.url)
    return deduped


def _empty_page_payload(url: str, page_type: str, *, status_code: int) -> PagePayload:
    return {
        "vendor_name": "",
        "website": url,
        "url": url,
        "page_type": page_type,
        "status_code": status_code,
        "html": "",
        "text": "",
    }


def _store_page_payload(
    candidate: _LinkCandidate,
    page_payload: PagePayload,
    *,
    named_pages: dict[str, PagePayload],
    extra_pages: list[PagePayload],
) -> None:
    if candidate.page_key in {
        "pricing_page",
        "product_page",
        "case_studies_page",
        "testimonials_page",
        "blog_page",
        "security_page",
        "about_page",
        "team_page",
        "contact_page",
        "demo_page",
        "help_page",
        "support_page",
        "developer_docs_page",
        "integrations_page",
    } and candidate.page_key not in named_pages:
        named_pages[candidate.page_key] = page_payload
        return

    page_url = str(page_payload.get("website") or page_payload.get("url") or "").strip()
    if page_url and all(str(item.get("website") or item.get("url") or "").strip() != page_url for item in extra_pages):
        extra_pages.append(page_payload)


def _assemble_explored_pages(
    *,
    homepage_payload: PagePayload,
    extra_pages: list[PagePayload],
    named_pages: dict[str, PagePayload],
    page_priority: tuple[str, ...],
) -> ExploredPages:
    explored_pages: ExploredPages = {
        "homepage": homepage_payload,
        "extra_pages": extra_pages,
    }
    for page_key in page_priority:
        if page_key in named_pages:
            explored_pages[page_key] = named_pages[page_key]
    for page_key, page_payload in named_pages.items():
        if page_key not in explored_pages:
            explored_pages[page_key] = page_payload
    return explored_pages


def _normalize_page_url(url: str) -> str:
    """Return a simple normalized URL without query strings."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""

    domain = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    if path == "/":
        path = ""
    return f"{parsed.scheme.lower()}://{domain}{path}"


def _normalized_domain(url: str) -> str:
    return normalize_domain(url)


def _is_allowed_site(url: str, homepage_domain: str, config: EnrichmentConfig) -> bool:
    candidate_domain = _normalized_domain(url)
    if candidate_domain == homepage_domain:
        return True
    if not candidate_domain or not homepage_domain:
        return False
    if _site_key(candidate_domain) != _site_key(homepage_domain):
        return False
    return any(candidate_domain.startswith(f"{subdomain}.") for subdomain in config.trusted_subdomains)


def _site_key(value: str) -> str:
    host = normalize_domain(value)
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) < 2:
        return host
    return ".".join(parts[-2:])


class _LinkParser(HTMLParser):
    """Collect homepage links and their visible anchor text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._current_href = ""
        self._current_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return

        self._current_href = ""
        self._current_parts = []
        for name, value in attrs:
            if name.lower() == "href" and value:
                self._current_href = value.strip()
                break

    def handle_data(self, data: str) -> None:
        if not self._current_href:
            return

        cleaned = " ".join(data.split())
        if cleaned:
            self._current_parts.append(cleaned)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._current_href:
            return

        anchor_text = " ".join(self._current_parts).strip()
        self.links.append((self._current_href, anchor_text))
        self._current_href = ""
        self._current_parts = []
