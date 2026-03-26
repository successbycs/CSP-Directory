"""M44: Junk domain enforcement — config-driven denylist with subdomain matching."""

from services.discovery.apify_sources import _is_denylisted_domain
from types import SimpleNamespace


def _config(*domains):
    return SimpleNamespace(junk_domain_denylist=domains)


# Exact domain matches
def test_blocks_exact_denylist_entry():
    config = _config("forbes.com", "gartner.com", "reddit.com")
    assert _is_denylisted_domain("forbes.com", config) is True


def test_blocks_www_prefix_of_denylist_entry():
    config = _config("forbes.com")
    assert _is_denylisted_domain("www.forbes.com", config) is True  # www.forbes.com is a subdomain match


def test_allows_unknown_domain():
    config = _config("forbes.com", "gartner.com")
    assert _is_denylisted_domain("gainsight.com", config) is False


# Subdomain matching
def test_blocks_subdomain_of_denylist_entry():
    config = _config("hubspot.com", "gainsight.com")
    assert _is_denylisted_domain("academy.hubspot.com", config) is True


def test_blocks_support_subdomain():
    config = _config("hubspot.com", "gainsight.com")
    assert _is_denylisted_domain("support.gainsight.com", config) is True


def test_blocks_deep_subdomain():
    config = _config("forbes.com")
    assert _is_denylisted_domain("news.tech.forbes.com", config) is True


def test_does_not_block_partial_domain_name_match():
    config = _config("reddit.com")
    assert _is_denylisted_domain("creddit.com", config) is False


def test_pipeline_config_is_single_source_of_truth():
    """pipeline_config.json junk_domain_denylist must contain key social/review/aggregator domains."""
    from services.config.load_config import load_pipeline_config
    config = load_pipeline_config()
    denylist = set(config.discovery.junk_domain_denylist)
    required = {"reddit.com", "linkedin.com", "gartner.com", "g2.com", "capterra.com"}
    missing = required - denylist
    assert not missing, f"Missing required junk domains from pipeline_config.json: {missing}"
