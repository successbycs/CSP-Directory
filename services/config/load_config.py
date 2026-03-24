"""Beginner-friendly loader for the repo-level pipeline config."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_CONFIG_PATH = PROJECT_ROOT / "config" / "pipeline_config.json"

DEFAULT_DISCOVERY_QUERIES = ("ai customer success platform",)
DEFAULT_SOURCE_ENGINE = "google_search"
DEFAULT_GOOGLE_SHEETS_COLUMNS = (
    "vendor_name",
    "website",
    "source",
    "mission",
    "usp",
    "icp",
    "use_cases",
    "lifecycle_stages",
    "pricing",
    "free_trial",
    "soc2",
    "founded",
    "case_studies",
    "customers",
    "value_statements",
    "confidence",
    "evidence_urls",
    "directory_fit",
    "directory_category",
    "include_in_directory",
)


@dataclass(frozen=True)
class DiscoveryConfig:
    queries: tuple[str, ...]
    source_engine: str
    actor_id: str
    max_pages_per_query: int
    results_per_page: int
    max_candidate_domains_per_run: int
    junk_domain_denylist: tuple[str, ...]
    article_path_hints: tuple[str, ...]
    content_hints: tuple[str, ...]
    product_hints: tuple[str, ...]
    customer_success_hints: tuple[str, ...]
    noise_subdomain_prefixes: tuple[str, ...]
    noise_domain_hints: tuple[str, ...]
    job_path_hints: tuple[str, ...]
    interstitial_hints: tuple[str, ...]


@dataclass(frozen=True)
class EnrichmentConfig:
    max_non_homepage_pages: int
    max_crawl_depth: int
    max_pages_total: int
    request_timeout_seconds: int
    discovery_mode: str
    sparse_link_threshold: int
    browser_discovery_timeout_ms: int
    browser_nav_labels: tuple[str, ...]
    external_fetch_backend: str
    external_fetch_actor_id: str
    external_fetch_max_pages: int
    external_fetch_use_proxy: bool
    page_priority: tuple[str, ...]
    page_patterns: dict[str, tuple[str, ...]]
    junk_hints: tuple[str, ...]
    blocklist_hints: tuple[str, ...]
    seed_paths: tuple[str, ...]
    trusted_subdomains: tuple[str, ...]


@dataclass(frozen=True)
class DirectoryRelevanceConfig:
    include_confidence_levels: tuple[str, ...]
    core_stages: tuple[str, ...]
    support_only_stages: tuple[str, ...]
    core_use_case_hints: tuple[str, ...]
    adjacent_use_case_hints: tuple[str, ...]
    infra_hints: tuple[str, ...]


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool
    model: str
    request_timeout_seconds: int
    max_page_text_chars: int
    max_site_text_chars: int
    max_error_body_chars: int


@dataclass(frozen=True)
class GoogleSheetsConfig:
    worksheet_name: str
    columns: tuple[str, ...]
    ops_review_enabled: bool
    runs_worksheet_name: str
    candidates_worksheet_name: str
    vendors_worksheet_name: str


@dataclass(frozen=True)
class PipelineConfig:
    discovery: DiscoveryConfig
    enrichment: EnrichmentConfig
    directory_relevance: DirectoryRelevanceConfig
    llm: LLMConfig
    google_sheets: GoogleSheetsConfig


def load_pipeline_config(config_path: Path | None = None) -> PipelineConfig:
    """Load and validate the repo-level pipeline config."""
    config_path = config_path or PIPELINE_CONFIG_PATH
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RuntimeError(f"Pipeline config was not found at {config_path}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Pipeline config at {config_path} is malformed JSON: {error}") from error

    if not isinstance(raw_config, dict):
        raise RuntimeError(f"Pipeline config at {config_path} must be a JSON object")

    return PipelineConfig(
        discovery=_load_discovery_config(raw_config, config_path),
        enrichment=_load_enrichment_config(raw_config, config_path),
        directory_relevance=_load_directory_relevance_config(raw_config, config_path),
        llm=_load_llm_config(raw_config, config_path),
        google_sheets=_load_google_sheets_config(raw_config, config_path),
    )


def _load_discovery_config(raw_config: dict[str, object], config_path: Path) -> DiscoveryConfig:
    discovery_config = _require_dict(raw_config, "discovery", config_path)
    return DiscoveryConfig(
        queries=_require_string_tuple(discovery_config, "queries", config_path),
        source_engine=_get_string(discovery_config, "source_engine", DEFAULT_SOURCE_ENGINE, config_path),
        actor_id=_get_string(discovery_config, "actor_id", "apify/google-search-scraper", config_path),
        max_pages_per_query=_get_int(discovery_config, "max_pages_per_query", 5, config_path),
        results_per_page=_get_int(discovery_config, "results_per_page", 10, config_path),
        max_candidate_domains_per_run=_get_int(
            discovery_config,
            "max_candidate_domains_per_run",
            100,
            config_path,
        ),
        junk_domain_denylist=_require_string_tuple(discovery_config, "junk_domain_denylist", config_path),
        article_path_hints=_require_string_tuple(discovery_config, "article_path_hints", config_path),
        content_hints=_require_string_tuple(discovery_config, "content_hints", config_path),
        product_hints=_require_string_tuple(discovery_config, "product_hints", config_path),
        customer_success_hints=_require_string_tuple(discovery_config, "customer_success_hints", config_path),
        noise_subdomain_prefixes=_require_string_tuple(discovery_config, "noise_subdomain_prefixes", config_path),
        noise_domain_hints=_require_string_tuple(discovery_config, "noise_domain_hints", config_path),
        job_path_hints=_require_string_tuple(discovery_config, "job_path_hints", config_path),
        interstitial_hints=_require_string_tuple(discovery_config, "interstitial_hints", config_path),
    )


def _load_enrichment_config(raw_config: dict[str, object], config_path: Path) -> EnrichmentConfig:
    enrichment_config = _require_dict(raw_config, "enrichment", config_path)
    page_patterns_raw = _require_dict(enrichment_config, "page_patterns", config_path)
    page_patterns = {
        page_key: _coerce_string_tuple(page_patterns_raw.get(page_key), config_path, f"enrichment.page_patterns.{page_key}")
        for page_key in page_patterns_raw
    }
    discovery_mode = _get_string(enrichment_config, "discovery_mode", "auto", config_path).lower()
    if discovery_mode not in {"auto", "html_only", "structured", "browser"}:
        raise RuntimeError(f"Pipeline config at {config_path} has invalid enrichment.discovery_mode")
    external_fetch_backend = _get_string(enrichment_config, "external_fetch_backend", "apify", config_path).lower()
    if external_fetch_backend not in {"none", "apify"}:
        raise RuntimeError(f"Pipeline config at {config_path} has invalid enrichment.external_fetch_backend")
    return EnrichmentConfig(
        max_non_homepage_pages=_get_int(enrichment_config, "max_non_homepage_pages", 5, config_path),
        max_crawl_depth=_get_int(enrichment_config, "max_crawl_depth", 1, config_path),
        max_pages_total=_get_int(
            enrichment_config,
            "max_pages_total",
            _get_int(enrichment_config, "max_non_homepage_pages", 5, config_path),
            config_path,
        ),
        request_timeout_seconds=_get_int(enrichment_config, "request_timeout_seconds", 10, config_path),
        discovery_mode=discovery_mode,
        sparse_link_threshold=_get_int(enrichment_config, "sparse_link_threshold", 3, config_path),
        browser_discovery_timeout_ms=_get_int(
            enrichment_config,
            "browser_discovery_timeout_ms",
            12000,
            config_path,
        ),
        browser_nav_labels=tuple(
            str(item).strip()
            for item in enrichment_config.get(
                "browser_nav_labels",
                ["Products", "Solutions", "Platform", "Resources", "Customers", "Company"],
            )
            if str(item).strip()
        ),
        external_fetch_backend=external_fetch_backend,
        external_fetch_actor_id=_get_string(
            enrichment_config,
            "external_fetch_actor_id",
            "apify/website-content-crawler",
            config_path,
        ),
        external_fetch_max_pages=_get_int(enrichment_config, "external_fetch_max_pages", 1, config_path),
        external_fetch_use_proxy=_get_bool(enrichment_config, "external_fetch_use_proxy", True, config_path),
        page_priority=_require_string_tuple(enrichment_config, "page_priority", config_path),
        page_patterns=page_patterns,
        junk_hints=_require_string_tuple(enrichment_config, "junk_hints", config_path),
        blocklist_hints=tuple(
            str(item).strip()
            for item in enrichment_config.get("blocklist_hints", [])
            if str(item).strip()
        ),
        seed_paths=tuple(
            str(item).strip()
            for item in enrichment_config.get("seed_paths", [])
            if str(item).strip()
        ),
        trusted_subdomains=tuple(
            str(item).strip()
            for item in enrichment_config.get("trusted_subdomains", [])
            if str(item).strip()
        ),
    )


def _load_directory_relevance_config(
    raw_config: dict[str, object],
    config_path: Path,
) -> DirectoryRelevanceConfig:
    relevance_config = _require_dict(raw_config, "directory_relevance", config_path)
    return DirectoryRelevanceConfig(
        include_confidence_levels=_require_string_tuple(
            relevance_config,
            "include_confidence_levels",
            config_path,
        ),
        core_stages=_require_string_tuple(relevance_config, "core_stages", config_path),
        support_only_stages=_require_string_tuple(relevance_config, "support_only_stages", config_path),
        core_use_case_hints=_require_string_tuple(relevance_config, "core_use_case_hints", config_path),
        adjacent_use_case_hints=_require_string_tuple(
            relevance_config,
            "adjacent_use_case_hints",
            config_path,
        ),
        infra_hints=_require_string_tuple(relevance_config, "infra_hints", config_path),
    )


def _load_llm_config(raw_config: dict[str, object], config_path: Path) -> LLMConfig:
    llm_config = _require_dict(raw_config, "llm", config_path)
    enabled = llm_config.get("enabled", True)
    if not isinstance(enabled, bool):
        raise RuntimeError(f"Pipeline config at {config_path} has invalid llm.enabled")
    return LLMConfig(
        enabled=enabled,
        model=_get_string(llm_config, "model", "gpt-5-mini", config_path),
        request_timeout_seconds=_get_int(llm_config, "request_timeout_seconds", 45, config_path),
        max_page_text_chars=_get_int(llm_config, "max_page_text_chars", 1800, config_path),
        max_site_text_chars=_get_int(llm_config, "max_site_text_chars", 8000, config_path),
        max_error_body_chars=_get_int(llm_config, "max_error_body_chars", 300, config_path),
    )


def _load_google_sheets_config(raw_config: dict[str, object], config_path: Path) -> GoogleSheetsConfig:
    sheets_config = _require_dict(raw_config, "google_sheets", config_path)
    columns = sheets_config.get("columns", list(DEFAULT_GOOGLE_SHEETS_COLUMNS))
    ops_review_enabled = sheets_config.get("ops_review_enabled", True)
    if not isinstance(ops_review_enabled, bool):
        raise RuntimeError(f"Pipeline config at {config_path} has invalid google_sheets.ops_review_enabled")
    return GoogleSheetsConfig(
        worksheet_name=_get_string(sheets_config, "worksheet_name", "vendors", config_path),
        columns=_coerce_string_tuple(columns, config_path, "google_sheets.columns"),
        ops_review_enabled=ops_review_enabled,
        runs_worksheet_name=_get_string(sheets_config, "runs_worksheet_name", "runs", config_path),
        candidates_worksheet_name=_get_string(
            sheets_config,
            "candidates_worksheet_name",
            "candidates",
            config_path,
        ),
        vendors_worksheet_name=_get_string(
            sheets_config,
            "vendors_worksheet_name",
            "vendors",
            config_path,
        ),
    )


def _get_bool(raw_config: dict[str, object], key: str, default: bool, config_path: Path) -> bool:
    value = raw_config.get(key, default)
    if isinstance(value, bool):
        return value
    raise RuntimeError(f"Pipeline config at {config_path} has invalid boolean key {key}")


def _require_dict(raw_config: dict[str, object], key: str, config_path: Path) -> dict[str, object]:
    value = raw_config.get(key)
    if not isinstance(value, dict):
        raise RuntimeError(f"Pipeline config at {config_path} is missing object key {key}")
    return value


def _get_string(container: dict[str, object], key: str, default: str, config_path: Path) -> str:
    value = container.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Pipeline config at {config_path} has invalid string key {key}")
    return value.strip()


def _get_int(container: dict[str, object], key: str, default: int, config_path: Path) -> int:
    value = container.get(key, default)
    if not isinstance(value, int):
        raise RuntimeError(f"Pipeline config at {config_path} has invalid integer key {key}")
    return value


def _require_string_tuple(
    container: dict[str, object],
    key: str,
    config_path: Path,
) -> tuple[str, ...]:
    return _coerce_string_tuple(container.get(key), config_path, key)


def _coerce_string_tuple(value: object, config_path: Path, key: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RuntimeError(f"Pipeline config at {config_path} has invalid list key {key}")
    cleaned_values = tuple(str(item).strip() for item in value if str(item).strip())
    if not cleaned_values:
        raise RuntimeError(f"Pipeline config at {config_path} has empty list key {key}")
    return cleaned_values
