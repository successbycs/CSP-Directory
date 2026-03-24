"""Helpers for loading repo-level enrichment configuration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import tomllib

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENRICHMENT_CONFIG_PATH = PROJECT_ROOT / "config" / "enrichment.toml"
DEFAULT_MAX_NON_HOMEPAGE_PAGES = 5
DEFAULT_MAX_CRAWL_DEPTH = 1
DEFAULT_MAX_PAGES_TOTAL = 5
DEFAULT_REQUEST_TIMEOUT_SECONDS = 10
DEFAULT_DISCOVERY_MODE = "auto"
DEFAULT_SPARSE_LINK_THRESHOLD = 3
DEFAULT_BROWSER_DISCOVERY_TIMEOUT_MS = 12000
DEFAULT_BROWSER_NAV_LABELS = ("Products", "Solutions", "Platform", "Resources", "Customers", "Company")
DEFAULT_SEED_PATHS = (
    "/about",
    "/about-us",
    "/our-story",
    "/contact",
    "/contact-us",
    "/pricing",
    "/blog",
    "/resources",
    "/documentation",
    "/docs",
    "/security",
    "/trust",
    "/customers",
    "/case-studies",
    "/testimonials",
)
DEFAULT_TRUSTED_SUBDOMAINS = ("docs", "help", "support", "blog")
DEFAULT_PAGE_PRIORITY = (
    "pricing_page",
    "product_page",
    "case_studies_page",
    "testimonials_page",
    "blog_page",
    "security_page",
    "about_page",
    "developer_docs_page",
    "integrations_page",
)
DEFAULT_PAGE_PATTERNS = {
    "pricing_page": ("pricing",),
    "product_page": ("product", "platform", "features", "solutions"),
    "case_studies_page": (
        "case studies",
        "case-study",
        "case-studies",
        "use cases",
        "use-case",
        "use-cases",
        "customer stories",
        "customer-story",
        "customers",
    ),
    "testimonials_page": ("testimonials", "testimonial", "reviews", "review"),
    "blog_page": ("blog", "blogs", "article", "articles", "insights", "news", "resources"),
    "about_page": ("about", "about us", "about-us", "company", "our story", "our-story"),
    "developer_docs_page": ("developer", "developers", "docs", "documentation", "api", "api-reference"),
    "security_page": ("security", "trust", "compliance"),
    "integrations_page": ("integrations", "integration", "apps", "marketplace"),
}
DEFAULT_JUNK_HINTS = (
    "careers",
    "career",
    "job",
    "jobs",
    "login",
    "signin",
    "sign-in",
)
DEFAULT_BLOCKLIST_HINTS = ("/legal", "privacy", "terms", "cookie")


@dataclass(frozen=True)
class SiteExplorerConfig:
    """Configurable limits and matching rules for site exploration."""

    max_non_homepage_pages: int = DEFAULT_MAX_NON_HOMEPAGE_PAGES
    max_crawl_depth: int = DEFAULT_MAX_CRAWL_DEPTH
    max_pages_total: int = DEFAULT_MAX_PAGES_TOTAL
    request_timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS
    discovery_mode: str = DEFAULT_DISCOVERY_MODE
    sparse_link_threshold: int = DEFAULT_SPARSE_LINK_THRESHOLD
    browser_discovery_timeout_ms: int = DEFAULT_BROWSER_DISCOVERY_TIMEOUT_MS
    browser_nav_labels: tuple[str, ...] = DEFAULT_BROWSER_NAV_LABELS
    page_priority: tuple[str, ...] = DEFAULT_PAGE_PRIORITY
    page_patterns: dict[str, tuple[str, ...]] | None = None
    junk_hints: tuple[str, ...] = DEFAULT_JUNK_HINTS
    blocklist_hints: tuple[str, ...] = DEFAULT_BLOCKLIST_HINTS
    seed_paths: tuple[str, ...] = DEFAULT_SEED_PATHS
    trusted_subdomains: tuple[str, ...] = DEFAULT_TRUSTED_SUBDOMAINS

    def resolved_page_patterns(self) -> dict[str, tuple[str, ...]]:
        """Return the effective page-pattern map."""
        return self.page_patterns or DEFAULT_PAGE_PATTERNS


def load_site_explorer_config(config_path: Path | None = None) -> SiteExplorerConfig:
    """Load site exploration settings from TOML."""
    config_path = config_path or ENRICHMENT_CONFIG_PATH
    if not config_path.exists():
        return SiteExplorerConfig(page_patterns=DEFAULT_PAGE_PATTERNS)

    try:
        with config_path.open("rb") as config_file:
            raw_config = tomllib.load(config_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        logger.warning("Could not load enrichment config at %s: %s", config_path, error)
        return SiteExplorerConfig(page_patterns=DEFAULT_PAGE_PATTERNS)

    explorer_config = raw_config.get("site_explorer", {})
    if not isinstance(explorer_config, dict):
        logger.warning("Enrichment config at %s is missing [site_explorer]", config_path)
        return SiteExplorerConfig(page_patterns=DEFAULT_PAGE_PATTERNS)

    raw_patterns = explorer_config.get("page_patterns", {})
    discovery_mode = str(explorer_config.get("discovery_mode", DEFAULT_DISCOVERY_MODE)).strip().lower()
    if discovery_mode not in {"auto", "html_only", "structured", "browser"}:
        logger.warning(
            "Invalid site_explorer.discovery_mode in %s; using default %s",
            config_path,
            DEFAULT_DISCOVERY_MODE,
        )
        discovery_mode = DEFAULT_DISCOVERY_MODE
    return SiteExplorerConfig(
        max_non_homepage_pages=_bounded_int(
            explorer_config.get("max_non_homepage_pages", explorer_config.get("max_pages_per_vendor")),
            setting_name="site_explorer.max_non_homepage_pages",
            config_path=config_path,
            default=DEFAULT_MAX_NON_HOMEPAGE_PAGES,
            minimum=1,
            maximum=100,
        ),
        max_crawl_depth=_bounded_int(
            explorer_config.get("max_crawl_depth"),
            setting_name="site_explorer.max_crawl_depth",
            config_path=config_path,
            default=DEFAULT_MAX_CRAWL_DEPTH,
            minimum=1,
            maximum=5,
        ),
        max_pages_total=_bounded_int(
            explorer_config.get("max_pages_total", explorer_config.get("max_non_homepage_pages")),
            setting_name="site_explorer.max_pages_total",
            config_path=config_path,
            default=DEFAULT_MAX_PAGES_TOTAL,
            minimum=1,
            maximum=100,
        ),
        request_timeout_seconds=_bounded_int(
            explorer_config.get("request_timeout_seconds"),
            setting_name="site_explorer.request_timeout_seconds",
            config_path=config_path,
            default=DEFAULT_REQUEST_TIMEOUT_SECONDS,
            minimum=1,
            maximum=60,
        ),
        discovery_mode=discovery_mode,
        sparse_link_threshold=_bounded_int(
            explorer_config.get("sparse_link_threshold"),
            setting_name="site_explorer.sparse_link_threshold",
            config_path=config_path,
            default=DEFAULT_SPARSE_LINK_THRESHOLD,
            minimum=1,
            maximum=20,
        ),
        browser_discovery_timeout_ms=_bounded_int(
            explorer_config.get("browser_discovery_timeout_ms"),
            setting_name="site_explorer.browser_discovery_timeout_ms",
            config_path=config_path,
            default=DEFAULT_BROWSER_DISCOVERY_TIMEOUT_MS,
            minimum=1000,
            maximum=60000,
        ),
        browser_nav_labels=_normalized_string_tuple(
            explorer_config.get("browser_nav_labels"),
            setting_name="site_explorer.browser_nav_labels",
            config_path=config_path,
            default=DEFAULT_BROWSER_NAV_LABELS,
        ),
        page_priority=_normalized_page_priority(
            explorer_config.get("page_priority"),
            config_path=config_path,
        ),
        page_patterns=_normalized_page_patterns(raw_patterns, config_path=config_path),
        junk_hints=_normalized_string_tuple(
            explorer_config.get("junk_hints"),
            setting_name="site_explorer.junk_hints",
            config_path=config_path,
            default=DEFAULT_JUNK_HINTS,
        ),
        blocklist_hints=_normalized_string_tuple(
            explorer_config.get("blocklist_hints"),
            setting_name="site_explorer.blocklist_hints",
            config_path=config_path,
            default=DEFAULT_BLOCKLIST_HINTS,
        ),
        seed_paths=_normalized_string_tuple(
            explorer_config.get("seed_paths"),
            setting_name="site_explorer.seed_paths",
            config_path=config_path,
            default=DEFAULT_SEED_PATHS,
        ),
        trusted_subdomains=_normalized_string_tuple(
            explorer_config.get("trusted_subdomains"),
            setting_name="site_explorer.trusted_subdomains",
            config_path=config_path,
            default=DEFAULT_TRUSTED_SUBDOMAINS,
        ),
    )


def _bounded_int(
    value: object,
    *,
    setting_name: str,
    config_path: Path,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if not isinstance(value, int):
        if value is not None:
            logger.warning(
                "Invalid %s in %s; expected an integer and using default %s",
                setting_name,
                config_path,
                default,
            )
        return default
    if value < minimum:
        logger.warning("%s in %s was below %s; using %s", setting_name, config_path, minimum, minimum)
        return minimum
    if value > maximum:
        logger.warning("%s in %s exceeded %s; using %s", setting_name, config_path, maximum, maximum)
        return maximum
    return value


def _normalized_page_priority(value: object, *, config_path: Path) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_PAGE_PRIORITY
    if not isinstance(value, list):
        logger.warning(
            "Invalid site_explorer.page_priority in %s; using defaults",
            config_path,
        )
        return DEFAULT_PAGE_PRIORITY

    cleaned = [str(item).strip() for item in value if str(item).strip() in DEFAULT_PAGE_PATTERNS]
    if not cleaned:
        logger.warning(
            "Invalid site_explorer.page_priority in %s; using defaults",
            config_path,
        )
        return DEFAULT_PAGE_PRIORITY
    return tuple(cleaned)


def _normalized_page_patterns(value: object, *, config_path: Path) -> dict[str, tuple[str, ...]]:
    if value is None:
        return DEFAULT_PAGE_PATTERNS
    if not isinstance(value, dict):
        logger.warning(
            "Invalid site_explorer.page_patterns in %s; using defaults",
            config_path,
        )
        return DEFAULT_PAGE_PATTERNS

    normalized_patterns: dict[str, tuple[str, ...]] = {}
    for page_key, default_patterns in DEFAULT_PAGE_PATTERNS.items():
        raw_patterns = value.get(page_key, default_patterns)
        if isinstance(raw_patterns, list):
            cleaned_patterns = tuple(str(item).strip().lower() for item in raw_patterns if str(item).strip())
            normalized_patterns[page_key] = cleaned_patterns or default_patterns
        else:
            normalized_patterns[page_key] = default_patterns
    return normalized_patterns


def _normalized_string_tuple(
    value: object,
    *,
    setting_name: str,
    config_path: Path,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    if value is None:
        return default
    if not isinstance(value, list):
        logger.warning("Invalid %s in %s; using defaults", setting_name, config_path)
        return default

    cleaned = tuple(str(item).strip().lower() for item in value if str(item).strip())
    if not cleaned:
        logger.warning("Invalid %s in %s; using defaults", setting_name, config_path)
        return default
    return cleaned
