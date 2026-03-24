"""Shared canonical normalization for vendor identity and contact fields."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_EMAIL_PATTERN = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}")
_DOMAIN_LABEL_PATTERN = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_PUNYCODE_TLD_PATTERN = re.compile(r"^xn--[a-z0-9-]{2,59}$")


def normalize_domain(value: object) -> str:
    """Return a canonical public domain when the input is valid."""
    text = str(value or "").strip()
    if not text:
        return ""

    candidate = text if "://" in text else f"https://{text}"
    parsed = urlparse(candidate)
    if parsed.username or parsed.password:
        return ""
    host = (parsed.hostname or "").strip().lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host or len(host) > 253:
        return ""

    labels = host.split(".")
    if len(labels) < 2:
        return ""

    for label in labels[:-1]:
        if not _DOMAIN_LABEL_PATTERN.fullmatch(label):
            return ""

    top_level_domain = labels[-1]
    if not (
        top_level_domain.isalpha()
        and 2 <= len(top_level_domain) <= 63
        or _PUNYCODE_TLD_PATTERN.fullmatch(top_level_domain)
    ):
        return ""
    return host


def normalize_website_url(value: object, *, keep_path: bool = True) -> str:
    """Return a canonical http(s) URL with a validated host."""
    text = str(value or "").strip()
    if not text:
        return ""

    candidate = text if "://" in text else f"https://{text}"
    parsed = urlparse(candidate)
    if parsed.username or parsed.password:
        return ""
    scheme = parsed.scheme.lower() or "https"
    if scheme not in {"http", "https"}:
        return ""

    domain = normalize_domain(parsed.hostname or "")
    if not domain:
        return ""

    path = parsed.path or ""
    if keep_path:
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        if path == "/":
            path = ""
    else:
        path = ""

    canonical_scheme = scheme if keep_path else "https"
    return f"{canonical_scheme}://{domain}{path}"


def normalize_vendor_website(value: object) -> str:
    """Return a canonical vendor homepage URL suitable for identity and dedupe."""
    return normalize_website_url(value, keep_path=False)


def normalize_email_address(value: object) -> str:
    """Return a canonical email address when the input is valid."""
    text = str(value or "").strip().lower()
    if not text or not _EMAIL_PATTERN.fullmatch(text):
        return ""
    return text


def normalize_email_list(value: object) -> list[str]:
    """Return a deduplicated list of canonical email addresses."""
    normalized: list[str] = []
    if isinstance(value, str):
        raw_values = [segment.strip() for segment in value.replace("\n", ",").replace("|", ",").split(",")]
    elif isinstance(value, list):
        raw_values = [str(item).strip() for item in value]
    else:
        raw_values = []

    for raw_value in raw_values:
        email_address = normalize_email_address(raw_value)
        if email_address and email_address not in normalized:
            normalized.append(email_address)
    return normalized


def normalize_phone_number(value: object) -> str:
    """Return a compact phone number string when the input looks valid."""
    text = str(value or "").strip()
    if not text:
        return ""

    has_plus = text.startswith("+")
    digits = re.sub(r"\D", "", text)
    if len(digits) < 10 or len(digits) > 15:
        return ""
    if not has_plus and len(digits) == 11 and digits.startswith("1"):
        has_plus = True
    return f"+{digits}" if has_plus else digits


def normalize_phone_numbers(value: object) -> list[str]:
    """Return a deduplicated list of canonical phone numbers."""
    normalized: list[str] = []
    if isinstance(value, str):
        raw_values = [segment.strip() for segment in value.replace("\n", ",").replace("|", ",").split(",")]
    elif isinstance(value, list):
        raw_values = [str(item).strip() for item in value]
    else:
        raw_values = []

    for raw_value in raw_values:
        phone_number = normalize_phone_number(raw_value)
        if phone_number and phone_number not in normalized:
            normalized.append(phone_number)
    return normalized


def company_name_from_website(value: object) -> str:
    """Build a simple fallback company name from a website or domain."""
    domain = normalize_domain(value)
    if not domain:
        return ""
    return domain.split(".")[0].replace("-", " ").title()
