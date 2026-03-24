"""Optional Level 2 LLM extraction for richer vendor intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import os
from typing import Any, Callable

import requests

from services.config.load_config import load_pipeline_config
from services.extraction.vendor_intel import (
    normalize_blog_posts,
    normalize_case_study_details,
    normalize_compliance_signals,
    normalize_email_list,
    normalize_icp_buyer_profiles,
    normalize_leadership_profiles,
    normalize_phone_numbers,
    normalize_product_profiles,
    normalize_testimonial_records,
)

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/responses"
DEFAULT_OPENAI_MODEL = load_pipeline_config().llm.model
MAX_PAGE_TEXT_CHARS = load_pipeline_config().llm.max_page_text_chars
MAX_SITE_TEXT_CHARS = load_pipeline_config().llm.max_site_text_chars
MAX_ERROR_BODY_CHARS = load_pipeline_config().llm.max_error_body_chars
_llm_is_disabled_for_run = False
_runtime_config_logged_for_run = False

PagePayload = dict[str, object]
ExploredPages = dict[str, PagePayload]
RequestPost = Callable[..., requests.Response]

LLM_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "is_cs_relevant": {"type": "boolean"},
        "mission": {"type": "string"},
        "usp": {"type": "string"},
        "icp": {
            "type": "array",
            "items": {"type": "string"},
        },
        "icp_buyer": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "persona": {"type": "string"},
                    "confidence": {"type": "string"},
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "google_queries": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "geo_queries": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["persona", "confidence", "evidence", "google_queries", "geo_queries"],
                "additionalProperties": False,
            },
        },
        "use_cases": {
            "type": "array",
            "items": {"type": "string"},
        },
        "lifecycle_stages": {
            "type": "array",
            "items": {"type": "string"},
        },
        "pricing": {
            "type": "array",
            "items": {"type": "string"},
        },
        "free_trial": {"type": ["boolean", "null"]},
        "soc2": {"type": ["boolean", "null"]},
        "compliance": {
            "type": "array",
            "items": {"type": "string"},
        },
        "founded": {"type": "string"},
        "products": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "use_cases": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "integration_categories": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "integrations": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "demo_url": {"type": "string"},
                    "support_url": {"type": "string"},
                    "help_center_url": {"type": "string"},
                    "developer_docs_url": {"type": "string"},
                    "source_url": {"type": "string"},
                },
                "required": [
                    "name",
                    "category",
                    "description",
                    "use_cases",
                    "integration_categories",
                    "integrations",
                    "demo_url",
                    "support_url",
                    "help_center_url",
                    "developer_docs_url",
                    "source_url",
                ],
                "additionalProperties": False,
            },
        },
        "leadership": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "title": {"type": "string"},
                    "source_url": {"type": "string"},
                },
                "required": ["name", "title", "source_url"],
                "additionalProperties": False,
            },
        },
        "ceo_name": {"type": "string"},
        "hq_address": {"type": "string"},
        "phone_numbers": {
            "type": "array",
            "items": {"type": "string"},
        },
        "contact_emails": {
            "type": "array",
            "items": {"type": "string"},
        },
        "company_hq": {"type": "string"},
        "contact_email": {"type": "string"},
        "developer_docs_url": {"type": "string"},
        "integration_categories": {
            "type": "array",
            "items": {"type": "string"},
        },
        "integrations": {
            "type": "array",
            "items": {"type": "string"},
        },
        "support_signals": {
            "type": "array",
            "items": {"type": "string"},
        },
        "case_studies": {
            "type": "array",
            "items": {"type": "string"},
        },
        "testimonials": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "proof_type": {"type": "string"},
                    "summary": {"type": "string"},
                    "quote": {"type": "string"},
                    "source_url": {"type": "string"},
                    "date": {"type": "string"},
                },
                "required": ["company", "proof_type", "summary", "quote", "source_url", "date"],
                "additionalProperties": False,
            },
        },
        "blog_posts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "summary": {"type": "string"},
                    "summary_word_count": {"type": "integer"},
                    "customer_name": {"type": "string"},
                    "value_statements": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "source_url": {"type": "string"},
                },
                "required": [
                    "title",
                    "body",
                    "summary",
                    "summary_word_count",
                    "customer_name",
                    "value_statements",
                    "source_url",
                ],
                "additionalProperties": False,
            },
        },
        "case_study_details": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "client": {"type": "string"},
                    "title": {"type": "string"},
                    "use_case": {"type": "string"},
                    "value_realized": {"type": "string"},
                    "metric": {"type": "string"},
                    "source_url": {"type": "string"},
                },
                "required": ["client", "title", "use_case", "value_realized", "source_url"],
                "additionalProperties": False,
            },
        },
        "customers": {
            "type": "array",
            "items": {"type": "string"},
        },
        "value_statements": {
            "type": "array",
            "items": {"type": "string"},
        },
        "source_urls": {
            "type": "array",
            "items": {"type": "string"},
        },
        "confidence": {"type": "string"},
    },
    "required": [
        "is_cs_relevant",
        "mission",
        "usp",
        "icp",
        "icp_buyer",
        "use_cases",
        "lifecycle_stages",
        "pricing",
        "free_trial",
        "soc2",
        "compliance",
        "founded",
        "products",
        "leadership",
        "ceo_name",
        "hq_address",
        "phone_numbers",
        "contact_emails",
        "company_hq",
        "contact_email",
        "developer_docs_url",
        "integration_categories",
        "integrations",
        "support_signals",
        "case_studies",
        "testimonials",
        "blog_posts",
        "case_study_details",
        "customers",
        "value_statements",
        "source_urls",
        "confidence",
    ],
    "additionalProperties": False,
}


@dataclass
class LLMExtractionResult:
    """Structured vendor intelligence returned by the LLM."""

    is_cs_relevant: bool = True
    mission: str = ""
    usp: str = ""
    icp: list[str] = field(default_factory=list)
    icp_buyer: list[dict[str, Any]] = field(default_factory=list)
    use_cases: list[str] = field(default_factory=list)
    lifecycle_stages: list[str] = field(default_factory=list)
    pricing: list[str] = field(default_factory=list)
    free_trial: bool | None = None
    soc2: bool | None = None
    compliance: list[str] = field(default_factory=list)
    founded: str = ""
    products: list[dict[str, Any]] = field(default_factory=list)
    leadership: list[dict[str, Any]] = field(default_factory=list)
    ceo_name: str = ""
    hq_address: str = ""
    phone_numbers: list[str] = field(default_factory=list)
    contact_emails: list[str] = field(default_factory=list)
    company_hq: str = ""
    contact_email: str = ""
    developer_docs_url: str = ""
    integration_categories: list[str] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)
    support_signals: list[str] = field(default_factory=list)
    case_studies: list[str] = field(default_factory=list)
    testimonials: list[dict[str, Any]] = field(default_factory=list)
    blog_posts: list[dict[str, Any]] = field(default_factory=list)
    case_study_details: list[dict[str, Any]] = field(default_factory=list)
    customers: list[str] = field(default_factory=list)
    value_statements: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    confidence: str = ""


def is_configured() -> bool:
    """Return True when OpenAI configuration is available."""
    return load_pipeline_config().llm.enabled and bool(os.getenv("OPENAI_API_KEY", "").strip())


def get_configured_model() -> str:
    """Return the configured OpenAI model name."""
    configured_model = os.getenv("OPENAI_MODEL", "").strip()
    return configured_model or load_pipeline_config().llm.model


def get_missing_configuration() -> list[str]:
    """Return required OpenAI configuration keys that are missing."""
    missing: list[str] = []
    if not os.getenv("OPENAI_API_KEY", "").strip():
        missing.append("OPENAI_API_KEY")
    return missing


def start_pipeline_run() -> None:
    """Reset LLM runtime state for a new pipeline run."""
    global _llm_is_disabled_for_run
    global _runtime_config_logged_for_run

    _llm_is_disabled_for_run = False
    _runtime_config_logged_for_run = False


def log_runtime_configuration() -> None:
    """Log the effective OpenAI runtime configuration once per pipeline run."""
    global _runtime_config_logged_for_run

    if _runtime_config_logged_for_run:
        return

    logger.info(
        "OpenAI LLM extraction config: enabled=%s endpoint=%s model=%s timeout=%ss max_site_text_chars=%s missing=%s",
        is_configured(),
        OPENAI_API_URL,
        get_configured_model(),
        load_pipeline_config().llm.request_timeout_seconds,
        load_pipeline_config().llm.max_site_text_chars,
        ",".join(get_missing_configuration()) or "none",
    )
    _runtime_config_logged_for_run = True


def extract_vendor_intelligence(
    page_payload: dict[str, object],
    *,
    request_post: RequestPost | None = None,
) -> LLMExtractionResult | None:
    """Extract richer vendor intelligence with the OpenAI API when configured."""
    global _llm_is_disabled_for_run

    if not is_configured() or _llm_is_disabled_for_run:
        return None

    site_text = _build_site_text(page_payload)
    if not site_text:
        return None

    request_post = request_post or requests.post
    llm_config = load_pipeline_config().llm
    headers = {
        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": get_configured_model(),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "vendor_intelligence",
                "schema": LLM_RESULT_SCHEMA,
                "strict": True,
            }
        },
        "input": [
            {
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You review vendor-level website evidence for an AI Customer Success vendor directory. "
                            "Be conservative. Use only the provided website text bundle. "
                            "Do not invent unsupported claims. Leave fields empty when the evidence is weak or missing. "
                            "Mark is_cs_relevant false unless the company clearly sells software or AI-enabled products "
                            "relevant to the customer success lifecycle. "
                            'Confidence must be one of "low", "medium", or "high". '
                            "Lifecycle stages are part of this task and should be multi-label when the evidence supports it."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Review this crawled website evidence and extract vendor intelligence.\n"
                            "Return the structured result using the provided schema.\n"
                            "Requirements:\n"
                            "- icp_buyer must be an array of buyer persona objects with persona, confidence, evidence, google_queries, and geo_queries\n"
                            "- google_queries and geo_queries must each contain up to 5 realistic searches/prompts the buyer would use to find this vendor category\n"
                            "- buyer personas should reflect who the website messaging is aimed at, not generic end users\n"
                            "- icp, lifecycle_stages, compliance, case_studies, customers, value_statements, and source_urls must be arrays of short strings\n"
                            "- pricing must be an array of short pricing signals like contact sales, per seat, per user, per month, or per year\n"
                            "- products must be structured product rows with name, category, description, use_cases, integration_categories, integrations, demo_url, support_url, help_center_url, developer_docs_url, and source_url when the site names multiple products\n"
                            "- keep vendor-level fields for company-wide claims; use product rows only for product-specific use cases, integrations, or surfaces\n"
                            "- leadership must capture founder/CEO/executive evidence when the site states it\n"
                            "- ceo_name, hq_address, phone_numbers, contact_emails, company_hq, and contact_email should be populated only when explicitly supported by the website evidence\n"
                            "- developer_docs_url should only be populated when the site clearly links to developer or API documentation\n"
                            "- integration_categories and integrations must be arrays of short strings when integrations are explicit\n"
                            "- support_signals must capture help-center, knowledge-base, support-portal, or community/training evidence when present\n"
                            "- compliance should capture items like SOC 2, ISO 27001, HIPAA, GDPR, trust center, or security review when supported\n"
                            "- testimonials must capture company, proof_type, summary, quote, source_url, and date when available\n"
                            "- blog_posts must capture title, body, summary, summary_word_count, customer_name, value_statements, and source_url for blog/article/review pages when useful\n"
                            "- case_study_details must stay separate from vendor-level value_statements and capture client, use_case, value_realized, optional metric, and source_url\n"
                            "- founded should be a year or short founded string if present, else empty string\n"
                            "- booleans should be true, false, or null\n"
                            "- do not invent claims that are not supported by the evidence\n"
                            "- leave uncertain text fields empty rather than guessing\n"
                            "- confidence should reflect certainty that this is a relevant AI-enabled Customer Success vendor\n\n"
                            f"Website text:\n{site_text}"
                        ),
                    }
                ],
            },
        ],
    }

    try:
        response = request_post(
            OPENAI_API_URL,
            headers=headers,
            json=payload,
            timeout=llm_config.request_timeout_seconds,
        )
        if 400 <= response.status_code < 500 and response.status_code != 429:
            error_body = _response_body_snippet(response)
            logger.warning(
                "Disabling LLM extraction for the rest of this pipeline run after OpenAI returned %s: %s",
                response.status_code,
                error_body,
            )
            _llm_is_disabled_for_run = True
            return None
        response.raise_for_status()
        response_payload = response.json()
        content = _extract_response_text(response_payload)
        return _parse_result(content)
    except (requests.RequestException, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        logger.warning("LLM extraction unavailable, falling back to deterministic extraction: %s", error)
        return None


def _response_body_snippet(response: requests.Response) -> str:
    """Return a short response body snippet for error logging."""
    response_text = getattr(response, "text", "")
    if not isinstance(response_text, str):
        return ""
    response_text = response_text.strip().replace("\n", " ")
    return response_text[: load_pipeline_config().llm.max_error_body_chars]


def _build_site_text(page_payload: dict[str, object]) -> str:
    """Build a compact vendor-level text bundle from explored pages."""
    page_payloads = _coerce_page_payloads(page_payload)
    text_sections: list[str] = []

    ordered_page_keys = [
        "homepage",
        "product_page",
        "pricing_page",
        "case_studies_page",
        "testimonials_page",
        "blog_page",
        "about_page",
        "team_page",
        "contact_page",
        "demo_page",
        "help_page",
        "support_page",
        "developer_docs_page",
        "security_page",
        "integrations_page",
    ]
    ordered_page_keys.extend(
        page_key for page_key in page_payloads if page_key.startswith("extra_page_")
    )

    for page_key in ordered_page_keys:
        section_text = _truncate_page_text(str(page_payloads.get(page_key, {}).get("text", "")).strip())
        section_url = str(
            page_payloads.get(page_key, {}).get("website")
            or page_payloads.get(page_key, {}).get("url")
            or ""
        ).strip()
        if not section_text:
            continue

        label = page_key.replace("_", " ")
        if section_url:
            text_sections.append(f"[{label}] {section_url}\n{section_text}")
        else:
            text_sections.append(f"[{label}]\n{section_text}")

    combined_text = "\n\n".join(text_sections).strip()
    return combined_text[: load_pipeline_config().llm.max_site_text_chars]


def _truncate_page_text(text: str) -> str:
    """Return deterministic page text truncated to a bounded size."""
    return text[: load_pipeline_config().llm.max_page_text_chars].strip()


def _coerce_page_payloads(page_payload: dict[str, object]) -> ExploredPages:
    if "homepage" in page_payload and isinstance(page_payload["homepage"], dict):
        page_payloads = {
            page_name: page_value
            for page_name, page_value in page_payload.items()
            if isinstance(page_value, dict)
        }
        extra_pages = page_payload.get("extra_pages", [])
        if isinstance(extra_pages, list):
            for index, extra_page in enumerate(extra_pages, start=1):
                if isinstance(extra_page, dict):
                    page_payloads[f"extra_page_{index}"] = extra_page
        return page_payloads
    return {"homepage": page_payload}


def _extract_response_text(response_payload: dict[str, Any]) -> str:
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output_items = response_payload.get("output")
    if not isinstance(output_items, list):
        raise ValueError("OpenAI response did not include output text")

    for item in output_items:
        if not isinstance(item, dict):
            continue

        content_parts = item.get("content")
        if not isinstance(content_parts, list):
            continue

        for part in content_parts:
            if not isinstance(part, dict):
                continue

            if part.get("type") != "output_text":
                continue

            text = part.get("text")
            if isinstance(text, str) and text.strip():
                return text

    raise ValueError("OpenAI response did not include output text")


def _parse_result(content: str) -> LLMExtractionResult:
    raw_result = json.loads(content)
    if not isinstance(raw_result, dict):
        raise ValueError("LLM extraction response was not a JSON object")

    confidence = str(raw_result.get("confidence", "")).strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = ""

    return LLMExtractionResult(
        is_cs_relevant=_normalize_required_bool(raw_result.get("is_cs_relevant"), default=True),
        mission=_clean_string(raw_result.get("mission")),
        usp=_clean_string(raw_result.get("usp")),
        icp=_normalize_string_list(raw_result.get("icp")),
        icp_buyer=normalize_icp_buyer_profiles(raw_result.get("icp_buyer")),
        use_cases=_normalize_string_list(raw_result.get("use_cases")),
        lifecycle_stages=_normalize_string_list(raw_result.get("lifecycle_stages")),
        pricing=_normalize_string_list(raw_result.get("pricing")),
        free_trial=_normalize_optional_bool(raw_result.get("free_trial")),
        soc2=_normalize_optional_bool(raw_result.get("soc2")),
        compliance=normalize_compliance_signals(raw_result.get("compliance")),
        founded=_clean_string(raw_result.get("founded")),
        products=normalize_product_profiles(raw_result.get("products")),
        leadership=normalize_leadership_profiles(raw_result.get("leadership")),
        ceo_name=_clean_string(raw_result.get("ceo_name")),
        hq_address=_clean_string(raw_result.get("hq_address")),
        phone_numbers=normalize_phone_numbers(raw_result.get("phone_numbers")),
        contact_emails=normalize_email_list(raw_result.get("contact_emails")),
        company_hq=_clean_string(raw_result.get("company_hq")),
        contact_email=_clean_string(raw_result.get("contact_email")),
        developer_docs_url=_clean_string(raw_result.get("developer_docs_url")),
        integration_categories=_normalize_string_list(raw_result.get("integration_categories")),
        integrations=_normalize_string_list(raw_result.get("integrations")),
        support_signals=_normalize_string_list(raw_result.get("support_signals")),
        case_studies=_normalize_string_list(raw_result.get("case_studies")),
        testimonials=normalize_testimonial_records(raw_result.get("testimonials")),
        blog_posts=normalize_blog_posts(raw_result.get("blog_posts")),
        case_study_details=normalize_case_study_details(raw_result.get("case_study_details")),
        customers=_normalize_string_list(raw_result.get("customers")),
        value_statements=_normalize_string_list(raw_result.get("value_statements")),
        source_urls=_normalize_string_list(raw_result.get("source_urls")),
        confidence=confidence,
    )


def _clean_string(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        candidates = [segment.strip() for segment in value.replace("\n", ",").replace("|", ",").split(",")]
        return [candidate for candidate in candidates if candidate]

    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            cleaned_item = _clean_string(item)
            if cleaned_item and cleaned_item not in normalized:
                normalized.append(cleaned_item)
        return normalized

    return []


def _normalize_optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None

    normalized = str(value).strip().lower()
    if normalized in {"true", "yes"}:
        return True
    if normalized in {"false", "no"}:
        return False
    return None


def _normalize_required_bool(value: object, *, default: bool) -> bool:
    normalized_value = _normalize_optional_bool(value)
    if normalized_value is None:
        return default
    return normalized_value
