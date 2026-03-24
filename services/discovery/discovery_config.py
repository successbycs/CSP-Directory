"""Helpers for loading repo-level discovery configuration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import tomllib

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DISCOVERY_CONFIG_PATH = PROJECT_ROOT / "config" / "discovery.toml"
DEFAULT_GOOGLE_SEARCH_ACTOR = "apify/google-search-scraper"
DEFAULT_GOOGLE_SEARCH_PAGES = 20
DEFAULT_GOOGLE_RESULTS_PER_PAGE = 10
DEFAULT_GOOGLE_SEARCH_QUERIES = ("ai customer success platform",)
DEFAULT_MAX_CANDIDATE_DOMAINS_PER_RUN = 100
DEFAULT_DENYLISTED_DOMAINS = (
    "facebook.com",
    "gartner.com",
    "google.com",
    "instagram.com",
    "jobs.ca",
    "linkedin.com",
    "medium.com",
    "reddit.com",
    "substack.com",
    "slashdot.org",
    "sourceforge.net",
    "twitter.com",
    "toolify.ai",
    "wikipedia.org",
    "x.com",
    "youtube.com",
)
DEFAULT_ARTICLE_PATH_HINTS = (
    "/article",
    "/articles",
    "/blog",
    "/blogs",
    "/community",
    "/forum",
    "/forums",
    "/guide",
    "/guides",
    "/learn",
    "/news",
    "/resources",
)
DEFAULT_CONTENT_HINTS = (
    "best ",
    "blog",
    "careers",
    "case studies",
    "case study",
    "community",
    "compare",
    "comparison",
    "forum",
    "guide",
    "guides",
    "how to",
    "job application",
    "jobs",
    "listicle",
    "newsletter",
    "reddit",
    "review",
    "reviews",
    "top ",
    "vs ",
)
DEFAULT_PRODUCT_HINTS = (
    "automation",
    "copilot",
    "platform",
    "software",
    "solution",
    "solutions",
    "tool",
    "tools",
    "workspace",
)
DEFAULT_CUSTOMER_SUCCESS_HINTS = (
    "adoption nudge",
    "adoption nudges",
    "case study",
    "case studies",
    "churn",
    "conversational intelligence",
    "cross-sell",
    "customer health",
    "customer onboarding",
    "customer success",
    "expansion revenue",
    "forecasting",
    "handoff",
    "health score",
    "implementation portal",
    "implementation portals",
    "in-app guidance",
    "meeting summaries",
    "meeting summary",
    "nps",
    "onboarding automation",
    "playbook",
    "product walkthrough",
    "product walkthroughs",
    "psa",
    "reference management",
    "renewal",
    "retention",
    "risk alert",
    "risk alerts",
    "sales-to-cs",
    "support automation",
    "support platform",
    "ticket triage",
    "help desk",
    "agent assist",
    "knowledge base",
    "sentiment analysis",
    "stakeholder mapping",
    "time to value",
    "upsell",
    "usage analytics",
    "user education",
    "voice of customer",
    "voc",
)
DEFAULT_NOISE_SUBDOMAIN_PREFIXES = (
    "blog.",
    "careers.",
    "community.",
    "jobs.",
    "newsletter.",
)
DEFAULT_NOISE_DOMAIN_HINTS = (
    "greenhouse",
    "myworkdayjobs",
)
DEFAULT_JOB_PATH_HINTS = (
    "/career",
    "/careers",
    "/job",
    "/jobs",
)
DEFAULT_INTERSTITIAL_HINTS = (
    "403 forbidden",
    "access denied",
    "just a moment",
)
MIN_GOOGLE_SEARCH_PAGES = 1
MIN_GOOGLE_RESULTS_PER_PAGE = 1
MAX_GOOGLE_SEARCH_PAGES = 20
MAX_GOOGLE_RESULTS_PER_PAGE = 10
MAX_CANDIDATE_DOMAINS_PER_RUN = 500


@dataclass(frozen=True)
class GoogleSearchConfig:
    """Configurable limits for Apify Google Search discovery."""

    actor_id: str = DEFAULT_GOOGLE_SEARCH_ACTOR
    queries: tuple[str, ...] = DEFAULT_GOOGLE_SEARCH_QUERIES
    max_pages_per_query: int = DEFAULT_GOOGLE_SEARCH_PAGES
    results_per_page: int = DEFAULT_GOOGLE_RESULTS_PER_PAGE
    max_candidate_domains_per_run: int = DEFAULT_MAX_CANDIDATE_DOMAINS_PER_RUN
    denylisted_domains: tuple[str, ...] = DEFAULT_DENYLISTED_DOMAINS
    article_path_hints: tuple[str, ...] = DEFAULT_ARTICLE_PATH_HINTS
    content_hints: tuple[str, ...] = DEFAULT_CONTENT_HINTS
    product_hints: tuple[str, ...] = DEFAULT_PRODUCT_HINTS
    customer_success_hints: tuple[str, ...] = DEFAULT_CUSTOMER_SUCCESS_HINTS
    noise_subdomain_prefixes: tuple[str, ...] = DEFAULT_NOISE_SUBDOMAIN_PREFIXES
    noise_domain_hints: tuple[str, ...] = DEFAULT_NOISE_DOMAIN_HINTS
    job_path_hints: tuple[str, ...] = DEFAULT_JOB_PATH_HINTS
    interstitial_hints: tuple[str, ...] = DEFAULT_INTERSTITIAL_HINTS


def load_google_search_config(
    config_path: Path | None = None,
) -> GoogleSearchConfig:
    """Load Google Search discovery settings from TOML."""
    config_path = config_path or DISCOVERY_CONFIG_PATH
    if not config_path.exists():
        return GoogleSearchConfig()

    try:
        with config_path.open("rb") as config_file:
            raw_config = tomllib.load(config_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        logger.warning("Could not load discovery config at %s: %s", config_path, error)
        return GoogleSearchConfig()

    google_search_config = raw_config.get("google_search", {})
    if not isinstance(google_search_config, dict):
        logger.warning("Discovery config at %s is missing [google_search]", config_path)
        return GoogleSearchConfig()

    return GoogleSearchConfig(
        actor_id=_normalized_string(
            google_search_config.get("actor_id"),
            setting_name="google_search.actor_id",
            config_path=config_path,
            default=GoogleSearchConfig.actor_id,
        ),
        queries=_normalized_queries(
            google_search_config.get("queries"),
            setting_name="google_search.queries",
            config_path=config_path,
            default=GoogleSearchConfig.queries,
        ),
        max_pages_per_query=_bounded_int(
            google_search_config.get("max_pages_per_query"),
            setting_name="google_search.max_pages_per_query",
            config_path=config_path,
            default=GoogleSearchConfig.max_pages_per_query,
            minimum=MIN_GOOGLE_SEARCH_PAGES,
            maximum=MAX_GOOGLE_SEARCH_PAGES,
        ),
        results_per_page=_bounded_int(
            google_search_config.get("results_per_page"),
            setting_name="google_search.results_per_page",
            config_path=config_path,
            default=GoogleSearchConfig.results_per_page,
            minimum=MIN_GOOGLE_RESULTS_PER_PAGE,
            maximum=MAX_GOOGLE_RESULTS_PER_PAGE,
        ),
        max_candidate_domains_per_run=_bounded_int(
            google_search_config.get("max_candidate_domains_per_run"),
            setting_name="google_search.max_candidate_domains_per_run",
            config_path=config_path,
            default=GoogleSearchConfig.max_candidate_domains_per_run,
            minimum=1,
            maximum=MAX_CANDIDATE_DOMAINS_PER_RUN,
        ),
        denylisted_domains=_normalized_string_list(
            google_search_config.get("denylisted_domains"),
            setting_name="google_search.denylisted_domains",
            config_path=config_path,
            default=GoogleSearchConfig.denylisted_domains,
        ),
        article_path_hints=_normalized_string_list(
            google_search_config.get("article_path_hints"),
            setting_name="google_search.article_path_hints",
            config_path=config_path,
            default=GoogleSearchConfig.article_path_hints,
        ),
        content_hints=_normalized_string_list(
            google_search_config.get("content_hints"),
            setting_name="google_search.content_hints",
            config_path=config_path,
            default=GoogleSearchConfig.content_hints,
        ),
        product_hints=_normalized_string_list(
            google_search_config.get("product_hints"),
            setting_name="google_search.product_hints",
            config_path=config_path,
            default=GoogleSearchConfig.product_hints,
        ),
        customer_success_hints=_normalized_string_list(
            google_search_config.get("customer_success_hints"),
            setting_name="google_search.customer_success_hints",
            config_path=config_path,
            default=GoogleSearchConfig.customer_success_hints,
        ),
        noise_subdomain_prefixes=_normalized_string_list(
            google_search_config.get("noise_subdomain_prefixes"),
            setting_name="google_search.noise_subdomain_prefixes",
            config_path=config_path,
            default=GoogleSearchConfig.noise_subdomain_prefixes,
        ),
        noise_domain_hints=_normalized_string_list(
            google_search_config.get("noise_domain_hints"),
            setting_name="google_search.noise_domain_hints",
            config_path=config_path,
            default=GoogleSearchConfig.noise_domain_hints,
        ),
        job_path_hints=_normalized_string_list(
            google_search_config.get("job_path_hints"),
            setting_name="google_search.job_path_hints",
            config_path=config_path,
            default=GoogleSearchConfig.job_path_hints,
        ),
        interstitial_hints=_normalized_string_list(
            google_search_config.get("interstitial_hints"),
            setting_name="google_search.interstitial_hints",
            config_path=config_path,
            default=GoogleSearchConfig.interstitial_hints,
        ),
    )


def parse_google_search_queries(value: str) -> list[str]:
    """Split a comma-separated query string into a clean list."""
    return [query.strip() for query in value.split(",") if query.strip()]


def _bounded_int(
    value: object,
    *,
    setting_name: str,
    config_path: Path,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Return an integer kept within a safe range."""
    if not isinstance(value, int):
        logger.warning(
            "Invalid %s in %s; expected an integer and using default %s",
            setting_name,
            config_path,
            default,
        )
        return default
    if value < minimum:
        logger.warning(
            "%s in %s was below the minimum %s; using %s",
            setting_name,
            config_path,
            minimum,
            minimum,
        )
        return minimum
    if value > maximum:
        logger.warning(
            "%s in %s exceeded the maximum %s; using %s",
            setting_name,
            config_path,
            maximum,
            maximum,
        )
        return maximum
    return value


def _normalized_queries(
    value: object,
    *,
    setting_name: str,
    config_path: Path,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    """Normalize configured queries into a non-empty tuple."""
    if value is None:
        return default

    if isinstance(value, str):
        queries = parse_google_search_queries(value)
    elif isinstance(value, list):
        queries = [str(item).strip() for item in value if str(item).strip()]
    else:
        logger.warning(
            "Invalid %s in %s; expected a comma-separated string or list and using default %s",
            setting_name,
            config_path,
            ", ".join(default),
        )
        return default

    if not queries:
        logger.warning(
            "Invalid %s in %s; no usable queries found and using default %s",
            setting_name,
            config_path,
            ", ".join(default),
        )
        return default

    return tuple(queries)


def _normalized_string(
    value: object,
    *,
    setting_name: str,
    config_path: Path,
    default: str,
) -> str:
    """Normalize a required string setting."""
    if not isinstance(value, str) or not value.strip():
        if value is not None:
            logger.warning(
                "Invalid %s in %s; expected a non-empty string and using default %s",
                setting_name,
                config_path,
                default,
            )
        return default
    return value.strip()


def _normalized_string_list(
    value: object,
    *,
    setting_name: str,
    config_path: Path,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    """Normalize a config value into a non-empty tuple of strings."""
    if value is None:
        return default

    if isinstance(value, str):
        normalized_values = parse_google_search_queries(value)
    elif isinstance(value, list):
        normalized_values = [str(item).strip() for item in value if str(item).strip()]
    else:
        logger.warning(
            "Invalid %s in %s; expected a list or comma-separated string and using default %s",
            setting_name,
            config_path,
            ", ".join(default),
        )
        return default

    if not normalized_values:
        logger.warning(
            "Invalid %s in %s; no usable values found and using default %s",
            setting_name,
            config_path,
            ", ".join(default),
        )
        return default

    return tuple(normalized_values)
