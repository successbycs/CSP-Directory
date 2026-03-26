"""M45: Lifecycle stage enforcement — no vendor in directory without lifecycle stages."""

from services.extraction.vendor_intel import VendorIntelligence
from services.extraction.vendor_profile_builder import enforce_lifecycle_stage_gate


def _profile(**kwargs) -> VendorIntelligence:
    defaults = dict(
        vendor_name="TestVendor",
        website="https://testvendor.com",
        lifecycle_stages=[],
        include_in_directory=None,
        directory_reasoning=[],
    )
    defaults.update(kwargs)
    return VendorIntelligence(**defaults)


def test_vendor_with_no_lifecycle_stages_and_include_true_gets_excluded():
    profile = _profile(include_in_directory=True, lifecycle_stages=[])
    result = enforce_lifecycle_stage_gate(profile)
    assert result.include_in_directory is False


def test_vendor_with_no_lifecycle_stages_adds_reasoning():
    profile = _profile(include_in_directory=True, lifecycle_stages=[])
    result = enforce_lifecycle_stage_gate(profile)
    assert any("lifecycle_stage_gate" in r for r in result.directory_reasoning)


def test_vendor_with_lifecycle_stages_is_not_changed():
    profile = _profile(include_in_directory=True, lifecycle_stages=["onboard", "adopt"])
    result = enforce_lifecycle_stage_gate(profile)
    assert result.include_in_directory is True


def test_vendor_already_excluded_is_not_changed():
    profile = _profile(include_in_directory=False, lifecycle_stages=[])
    result = enforce_lifecycle_stage_gate(profile)
    assert result.include_in_directory is False


def test_vendor_with_none_include_in_directory_is_not_changed():
    profile = _profile(include_in_directory=None, lifecycle_stages=[])
    result = enforce_lifecycle_stage_gate(profile)
    assert result.include_in_directory is None


def test_existing_reasoning_is_preserved():
    profile = _profile(
        include_in_directory=True,
        lifecycle_stages=[],
        directory_reasoning=["Previous reason"],
    )
    result = enforce_lifecycle_stage_gate(profile)
    assert "Previous reason" in result.directory_reasoning
