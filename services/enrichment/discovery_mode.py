"""Discovery-mode helpers for blocked or JS-heavy vendor sites."""

from __future__ import annotations

from html.parser import HTMLParser
import logging
import re
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import requests

from services.extraction.identity import normalize_domain

if TYPE_CHECKING:
    from services.config.load_config import EnrichmentConfig

logger = logging.getLogger(__name__)

SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml")
SITEMAP_XML_HINT = "<?xml"
MAX_CHILD_SITEMAPS = 12
SCRIPT_URL_PATTERN = re.compile(
    r"""
    (?:
        ["']
        (?P<quoted>(?:https?://|/)[^"'#\s<>]+)
        ["']
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
DISALLOWED_DISCOVERY_EXTENSIONS = (
    ".css",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".map",
    ".pdf",
    ".png",
    ".svg",
    ".webp",
    ".xml",
)


def discover_vendor_links(
    homepage_payload: dict[str, object],
    config: EnrichmentConfig,
) -> list[tuple[str, str]]:
    """Return fallback links discovered from scripts, sitemap, or browser rendering."""
    if config.discovery_mode == "html_only":
        return []

    homepage_url = str(homepage_payload.get("website", "")).strip()
    homepage_html = str(homepage_payload.get("html", ""))
    if not homepage_url:
        return []

    discovered_links: list[tuple[str, str]] = []
    discovered_links.extend(_discover_script_links(homepage_url, homepage_html, config))

    if _should_probe_structured_fallback(homepage_payload, homepage_html, config):
        discovered_links.extend(_discover_sitemap_links(homepage_url, config))

    if _should_use_browser_discovery(homepage_payload, homepage_html, config):
        discovered_links.extend(_discover_links_with_browser(homepage_url, config))

    return _dedupe_links(discovered_links)


def fetch_page_with_browser(
    url: str,
    *,
    config: EnrichmentConfig,
) -> dict[str, object] | None:
    """Return rendered HTML/text for one page via Playwright."""
    if config.discovery_mode in {"html_only", "structured"}:
        return None

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as error:  # pragma: no cover - environment-specific import path
        logger.info("Browser discovery unavailable for %s: %s", url, error)
        return None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(viewport={"width": 1440, "height": 1080})
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=config.browser_discovery_timeout_ms)
            _expand_nav_menus(page, config.browser_nav_labels)
            page.wait_for_timeout(500)
            html = page.content()
            text = page.locator("body").inner_text(timeout=config.browser_discovery_timeout_ms)
            status_code = response.status if response is not None else 200
            page.close()
            context.close()
            browser.close()
    except PlaywrightTimeoutError as error:  # pragma: no cover - runtime/browser-specific
        logger.info("Browser discovery timed out for %s: %s", url, error)
        return None
    except Exception as error:  # pragma: no cover - runtime/browser-specific
        logger.info("Browser discovery failed for %s: %s", url, error)
        return None

    if not html.strip() or not text.strip():
        return None

    return {
        "status_code": status_code,
        "html": html,
        "text": text,
        "fetch_backend": "playwright",
    }


def fetch_page_with_external_backend(
    url: str,
    *,
    config: EnrichmentConfig,
) -> dict[str, object] | None:
    """Return rendered HTML/text from the configured external backend."""
    if config.external_fetch_backend != "apify":
        return None

    try:
        from services.discovery import apify_sources

        return apify_sources.fetch_rendered_page(
            url,
            actor_id=config.external_fetch_actor_id,
            max_pages=config.external_fetch_max_pages,
            use_proxy=config.external_fetch_use_proxy,
        )
    except Exception as error:  # pragma: no cover - runtime/provider-specific
        logger.info("External fetch backend failed for %s: %s", url, error)
        return None


def fetch_page_with_fallback(
    url: str,
    *,
    config: EnrichmentConfig,
) -> dict[str, object] | None:
    """Return best-effort rendered content after local browser and external fallbacks."""
    browser_payload = fetch_page_with_browser(url, config=config)
    if browser_payload:
        return browser_payload
    return fetch_page_with_external_backend(url, config=config)


def _discover_script_links(
    homepage_url: str,
    homepage_html: str,
    config: EnrichmentConfig,
) -> list[tuple[str, str]]:
    if not homepage_html:
        return []

    homepage_domain = normalize_domain(homepage_url)
    discovered_links: list[tuple[str, str]] = []
    for match in SCRIPT_URL_PATTERN.finditer(homepage_html):
        raw_url = match.group("quoted") or ""
        normalized_url = _normalize_candidate_url(homepage_url, raw_url)
        if not normalized_url or not _is_allowed_site(normalized_url, homepage_domain, config):
            continue
        discovered_links.append((normalized_url, _anchor_label_from_url(normalized_url)))
    return discovered_links


def _discover_sitemap_links(
    homepage_url: str,
    config: EnrichmentConfig,
) -> list[tuple[str, str]]:
    homepage_domain = normalize_domain(homepage_url)
    discovered_links: list[tuple[str, str]] = []
    seen_sitemaps: set[str] = set()

    for sitemap_path in SITEMAP_PATHS:
        sitemap_url = urljoin(homepage_url, sitemap_path)
        discovered_links.extend(
            _discover_links_from_sitemap_url(
                sitemap_url,
                homepage_url=homepage_url,
                homepage_domain=homepage_domain,
                config=config,
                seen_sitemaps=seen_sitemaps,
                depth=0,
            )
        )

    return discovered_links


def _fetch_sitemap_xml(sitemap_url: str, *, timeout_seconds: int) -> str:
    try:
        response = requests.get(sitemap_url, timeout=timeout_seconds)
    except requests.RequestException as error:
        logger.info("Could not fetch sitemap %s: %s", sitemap_url, error)
        return ""

    if response.status_code >= 400:
        return ""
    if SITEMAP_XML_HINT not in response.text[:1000].lower() and "<urlset" not in response.text.lower():
        if "<sitemapindex" not in response.text.lower():
            return ""
    return response.text


def _discover_links_from_sitemap_url(
    sitemap_url: str,
    *,
    homepage_url: str,
    homepage_domain: str,
    config: EnrichmentConfig,
    seen_sitemaps: set[str],
    depth: int,
) -> list[tuple[str, str]]:
    normalized_sitemap_url = _normalize_fetch_url(homepage_url, sitemap_url)
    if not normalized_sitemap_url or normalized_sitemap_url in seen_sitemaps:
        return []
    seen_sitemaps.add(normalized_sitemap_url)

    xml_payload = _fetch_sitemap_xml(normalized_sitemap_url, timeout_seconds=config.request_timeout_seconds)
    if not xml_payload:
        return []
    return _extract_sitemap_links(
        homepage_url,
        xml_payload,
        homepage_domain,
        config,
        seen_sitemaps=seen_sitemaps,
        depth=depth,
    )


def _extract_sitemap_links(
    homepage_url: str,
    xml_payload: str,
    homepage_domain: str,
    config: EnrichmentConfig,
    *,
    seen_sitemaps: set[str],
    depth: int,
) -> list[tuple[str, str]]:
    try:
        root = ET.fromstring(xml_payload)
    except ET.ParseError:
        return []

    namespace = ""
    if root.tag.startswith("{"):
        namespace = root.tag.split("}", 1)[0] + "}"

    if root.tag.endswith("sitemapindex") and depth < 1:
        discovered_links: list[tuple[str, str]] = []
        child_sitemap_locs = root.findall(f".//{namespace}loc")
        for loc in child_sitemap_locs[:MAX_CHILD_SITEMAPS]:
            child_sitemap_url = (loc.text or "").strip()
            if not child_sitemap_url:
                continue
            discovered_links.extend(
                _discover_links_from_sitemap_url(
                    child_sitemap_url,
                    homepage_url=homepage_url,
                    homepage_domain=homepage_domain,
                    config=config,
                    seen_sitemaps=seen_sitemaps,
                    depth=depth + 1,
                )
            )
        return discovered_links

    discovered_links: list[tuple[str, str]] = []
    for loc in root.findall(f".//{namespace}loc"):
        raw_url = (loc.text or "").strip()
        normalized_url = _normalize_candidate_url(homepage_url, raw_url)
        if not normalized_url or not _is_allowed_site(normalized_url, homepage_domain, config):
            continue
        discovered_links.append((normalized_url, _anchor_label_from_url(normalized_url)))

    return discovered_links


def _discover_links_with_browser(
    homepage_url: str,
    config: EnrichmentConfig,
) -> list[tuple[str, str]]:
    browser_payload = fetch_page_with_browser(homepage_url, config=config)
    if not browser_payload:
        return []

    homepage_html = str(browser_payload.get("html", ""))
    homepage_domain = normalize_domain(homepage_url)
    link_parser = _LinkParser()
    link_parser.feed(homepage_html)
    link_parser.close()

    discovered_links: list[tuple[str, str]] = []
    for href, anchor_text in link_parser.links:
        normalized_url = _normalize_candidate_url(homepage_url, href)
        if not normalized_url or not _is_allowed_site(normalized_url, homepage_domain, config):
            continue
        discovered_links.append((normalized_url, anchor_text or _anchor_label_from_url(normalized_url)))
    return discovered_links


def _should_probe_structured_fallback(
    homepage_payload: dict[str, object],
    homepage_html: str,
    config: EnrichmentConfig,
) -> bool:
    if config.discovery_mode in {"structured", "browser"}:
        return True
    return _looks_blocked_or_sparse(homepage_payload, homepage_html, config)


def _should_use_browser_discovery(
    homepage_payload: dict[str, object],
    homepage_html: str,
    config: EnrichmentConfig,
) -> bool:
    if config.discovery_mode == "browser":
        return True
    if config.discovery_mode != "auto":
        return False
    return _looks_blocked_or_sparse(homepage_payload, homepage_html, config)


def _looks_blocked_or_sparse(
    homepage_payload: dict[str, object],
    homepage_html: str,
    config: EnrichmentConfig,
) -> bool:
    status_code = int(homepage_payload.get("status_code", 0) or 0)
    if status_code == 0 or status_code >= 400:
        return True

    if not homepage_html:
        return True

    link_count = homepage_html.lower().count("<a ")
    return link_count < config.sparse_link_threshold


def _expand_nav_menus(page, nav_labels: tuple[str, ...]) -> None:
    for label in nav_labels:
        if not label:
            continue
        try:
            page.get_by_role("button", name=re.compile(re.escape(label), re.IGNORECASE)).first.click(timeout=750)
            page.wait_for_timeout(150)
            continue
        except Exception:
            pass
        try:
            page.get_by_role("link", name=re.compile(re.escape(label), re.IGNORECASE)).first.hover(timeout=750)
            page.wait_for_timeout(150)
        except Exception:
            continue


def _normalize_candidate_url(homepage_url: str, candidate: str) -> str:
    raw_candidate = str(candidate).strip()
    if not raw_candidate:
        return ""
    if raw_candidate.startswith(("mailto:", "tel:", "#", "javascript:")):
        return ""

    normalized_url = urljoin(homepage_url, raw_candidate)
    parsed = urlparse(normalized_url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    if parsed.scheme not in {"http", "https"}:
        return ""

    lowered_path = parsed.path.lower()
    if any(lowered_path.endswith(extension) for extension in DISALLOWED_DISCOVERY_EXTENSIONS):
        return ""

    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    if path == "/":
        path = ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


def _normalize_fetch_url(homepage_url: str, candidate: str) -> str:
    raw_candidate = str(candidate).strip()
    if not raw_candidate:
        return ""

    normalized_url = urljoin(homepage_url, raw_candidate)
    parsed = urlparse(normalized_url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    if parsed.scheme not in {"http", "https"}:
        return ""

    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    if path == "/":
        path = ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


def _is_allowed_site(url: str, homepage_domain: str, config: EnrichmentConfig) -> bool:
    candidate_domain = normalize_domain(url)
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


def _anchor_label_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return "homepage"
    return path.split("/")[-1].replace("-", " ").replace("_", " ").strip()


def _dedupe_links(links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    deduped: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    for url, label in links:
        if url in seen_urls:
            continue
        deduped.append((url, label))
        seen_urls.add(url)
    return deduped


class _LinkParser(HTMLParser):
    """Collect links from HTML content."""

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
        self.links.append((self._current_href, " ".join(self._current_parts).strip()))
        self._current_href = ""
        self._current_parts = []
