"""Deterministic directory relevance scoring for enriched vendor profiles."""

from __future__ import annotations

from dataclasses import dataclass, field

from services.config.load_config import DirectoryRelevanceConfig, load_pipeline_config
from services.extraction.vendor_intel import VendorIntelligence


@dataclass(frozen=True)
class DirectoryRelevanceDecision:
    """Structured auto-decision for directory inclusion governance."""

    directory_fit: str
    directory_category: str
    include_in_directory: bool
    reasoning: list[str] = field(default_factory=list)
    decision_source: str = "auto"


def evaluate_directory_relevance(
    intelligence: VendorIntelligence,
    config: DirectoryRelevanceConfig | None = None,
) -> tuple[str, str, bool]:
    """Return directory fit, category, and include flag from deterministic signals."""
    decision = evaluate_directory_relevance_decision(intelligence, config=config)
    return decision.directory_fit, decision.directory_category, decision.include_in_directory


def evaluate_directory_relevance_decision(
    intelligence: VendorIntelligence,
    config: DirectoryRelevanceConfig | None = None,
) -> DirectoryRelevanceDecision:
    """Return a structured directory-governance decision plus operator-facing reasoning."""
    config = config or load_pipeline_config().directory_relevance

    confidence = intelligence.confidence.strip().lower()
    stages = tuple(stage for stage in intelligence.lifecycle_stages if stage)
    signal_text = _signal_text(intelligence).lower()

    has_core_stage = any(stage in config.core_stages for stage in stages)
    has_support_only_stage = bool(stages) and all(stage in config.support_only_stages for stage in stages)
    has_core_use_case = any(hint in signal_text for hint in config.core_use_case_hints)
    has_adjacent_use_case = any(hint in signal_text for hint in config.adjacent_use_case_hints)
    has_infra_hint = any(hint in signal_text for hint in config.infra_hints)
    matched_core_hints = _matched_hints(signal_text, config.core_use_case_hints)
    matched_adjacent_hints = _matched_hints(signal_text, config.adjacent_use_case_hints)
    matched_infra_hints = _matched_hints(signal_text, config.infra_hints)
    has_customer_success_signal = any(
        hint in signal_text
        for hint in (
            "customer success",
            "renewal",
            "onboarding",
            "adoption",
            "retention",
            "customer health",
            "churn",
            "voice of customer",
            "advocacy",
        )
    )
    has_generic_cx_hint = any(
        hint in signal_text
        for hint in (
            "customer experience",
            "cx platform",
            "contact center",
            "call center",
            "help desk",
        )
    )

    if has_infra_hint and not (has_core_stage or has_core_use_case or has_adjacent_use_case):
        return DirectoryRelevanceDecision(
            directory_fit="low",
            directory_category="infra",
            include_in_directory=False,
            reasoning=[
                f"Matched infrastructure hints: {', '.join(matched_infra_hints[:3])}.",
                "No core or adjacent customer-success signals were strong enough to include the vendor.",
            ],
        )

    if has_core_stage or has_core_use_case:
        include = confidence in config.include_confidence_levels
        fit = "high" if confidence == "high" else "medium"
        reasoning = []
        if has_core_stage:
            reasoning.append(f"Mapped to core lifecycle stages: {', '.join(stages[:3])}.")
        if matched_core_hints:
            reasoning.append(f"Matched core customer-success hints: {', '.join(matched_core_hints[:3])}.")
        reasoning.append(
            "Confidence meets inclusion threshold." if include else "Signals look core, but confidence is below the inclusion threshold."
        )
        return DirectoryRelevanceDecision(
            directory_fit=fit,
            directory_category="cs_core",
            include_in_directory=include,
            reasoning=reasoning,
        )

    if has_support_only_stage:
        include = confidence in config.include_confidence_levels
        fit = "medium" if include else "low"
        return DirectoryRelevanceDecision(
            directory_fit=fit,
            directory_category="support_only",
            include_in_directory=include,
            reasoning=[
                f"Lifecycle mapping is support-only: {', '.join(stages[:3])}.",
                "Confidence meets inclusion threshold." if include else "Support-only signal is present, but confidence is below the inclusion threshold.",
            ],
        )

    if has_adjacent_use_case or has_customer_success_signal:
        include = confidence in config.include_confidence_levels
        fit = "medium" if include else "low"
        reasoning = []
        if matched_adjacent_hints:
            reasoning.append(f"Matched adjacent customer-success hints: {', '.join(matched_adjacent_hints[:3])}.")
        if has_customer_success_signal:
            reasoning.append("Mission or value-proof text contains broader customer-success signals.")
        reasoning.append(
            "Confidence meets inclusion threshold." if include else "Adjacent relevance is present, but confidence is below the inclusion threshold."
        )
        return DirectoryRelevanceDecision(
            directory_fit=fit,
            directory_category="cs_adjacent",
            include_in_directory=include,
            reasoning=reasoning,
        )

    if has_generic_cx_hint:
        return DirectoryRelevanceDecision(
            directory_fit="low",
            directory_category="generic_cx",
            include_in_directory=False,
            reasoning=["Matched generic CX or support language without strong customer-success workflow evidence."],
        )

    include = confidence in config.include_confidence_levels and bool(
        intelligence.mission.strip() or intelligence.usp.strip() or intelligence.value_statements or intelligence.case_studies
    )
    return DirectoryRelevanceDecision(
        directory_fit="medium" if include else "low",
        directory_category="cs_adjacent" if include else "infra",
        include_in_directory=include,
        reasoning=[
            "Fallback decision from overall mission/value-proof detail."
            if include
            else "Insufficient customer-success evidence for directory inclusion."
        ],
    )


def _signal_text(intelligence: VendorIntelligence) -> str:
    parts = [
        intelligence.mission,
        intelligence.usp,
        *intelligence.icp,
        *intelligence.value_statements,
        *intelligence.case_studies,
        *intelligence.customers,
    ]
    return " ".join(part.strip() for part in parts if part and part.strip())


def _matched_hints(signal_text: str, hints: tuple[str, ...]) -> list[str]:
    return [hint for hint in hints if hint in signal_text]
