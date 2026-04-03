"""Tests for M73a: feature_depth_score and feature_signals fields on VendorIntelligence."""
import pytest
from services.extraction.vendor_intel import VendorIntelligence


def _make_vi(**kwargs) -> VendorIntelligence:
    return VendorIntelligence(vendor_name="Test Vendor", website="https://example.com", **kwargs)


def test_feature_depth_score_defaults_none():
    vi = _make_vi()
    assert vi.feature_depth_score is None


def test_feature_signals_defaults_empty_list():
    vi = _make_vi()
    assert vi.feature_signals == []


def test_feature_depth_score_accepts_int():
    vi = _make_vi(feature_depth_score=7)
    assert vi.feature_depth_score == 7


def test_feature_signals_accepts_list():
    signals = ["health_scoring", "playbook_automation", "usage_analytics"]
    vi = _make_vi(feature_signals=signals)
    assert vi.feature_signals == signals


def test_feature_depth_score_accepts_zero():
    vi = _make_vi(feature_depth_score=0)
    assert vi.feature_depth_score == 0


def test_feature_depth_score_accepts_none_explicitly():
    vi = _make_vi(feature_depth_score=None)
    assert vi.feature_depth_score is None
