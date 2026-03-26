"""M69: Exclude directory_category=other from public export."""

from services.export.directory_dataset import build_directory_dataset
from services.extraction.vendor_intel import VendorIntelligence


def _profile(vendor_name, directory_category, include_in_directory=True, lifecycle_stages=None):
    return VendorIntelligence(
        vendor_name=vendor_name,
        website=f"https://{vendor_name.lower()}.com",
        include_in_directory=include_in_directory,
        directory_category=directory_category,
        lifecycle_stages=lifecycle_stages or ["onboard"],
    )


def test_other_category_excluded_from_export():
    profiles = [
        _profile("GoodVendor", "csp"),
        _profile("OtherVendor", "other"),
    ]
    dataset = build_directory_dataset(fallback_profiles=profiles, prefer_fallback_profiles=True)
    names = [row["vendor_name"] for row in dataset]
    assert "GoodVendor" in names
    assert "OtherVendor" not in names


def test_non_other_categories_are_included():
    profiles = [
        _profile("CspVendor", "csp"),
        _profile("WorkflowVendor", "workflow"),
        _profile("PlatformVendor", "platform"),
    ]
    dataset = build_directory_dataset(fallback_profiles=profiles, prefer_fallback_profiles=True)
    names = [row["vendor_name"] for row in dataset]
    assert "CspVendor" in names
    assert "WorkflowVendor" in names
    assert "PlatformVendor" in names


def test_excluded_vendor_not_in_dataset_regardless_of_category():
    profiles = [
        _profile("ExcludedVendor", "csp", include_in_directory=False),
        _profile("IncludedVendor", "csp", include_in_directory=True),
    ]
    dataset = build_directory_dataset(fallback_profiles=profiles, prefer_fallback_profiles=True)
    names = [row["vendor_name"] for row in dataset]
    assert "ExcludedVendor" not in names
    assert "IncludedVendor" in names
