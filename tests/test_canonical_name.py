"""Unit tests for M43 canonical vendor name enforcement.

Tests that _name_fails_quality_check and _derive_canonical_name reject known-bad
names and produce clean canonical names.
"""

from __future__ import annotations

import sys
from pathlib import Path
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Stub supabase before importing the script so tests run without the package installed
_supabase_stub = mock.MagicMock()
sys.modules.setdefault("supabase", _supabase_stub)

from scripts.enrich_vendors_deterministic import _name_fails_quality_check, _derive_canonical_name


class NameQualityCheckTests(unittest.TestCase):
    def test_rejects_pipe_separator(self) -> None:
        self.assertTrue(_name_fails_quality_check("Vitally | Product Success Platform"))

    def test_rejects_em_dash_separator(self) -> None:
        self.assertTrue(_name_fails_quality_check("Gainsight — Customer Success"))

    def test_rejects_spaced_hyphen_separator(self) -> None:
        self.assertTrue(_name_fails_quality_check("Outreach - Sales Engagement"))

    def test_rejects_gt_separator(self) -> None:
        self.assertTrue(_name_fails_quality_check("Totango > Lifecycle Platform"))

    def test_rejects_name_over_60_chars(self) -> None:
        self.assertTrue(_name_fails_quality_check("A" * 61))

    def test_rejects_article_word_what(self) -> None:
        self.assertTrue(_name_fails_quality_check("What is Customer Success Software"))

    def test_rejects_article_word_best(self) -> None:
        self.assertTrue(_name_fails_quality_check("Best Customer Success Tools 2025"))

    def test_rejects_article_word_how(self) -> None:
        self.assertTrue(_name_fails_quality_check("How to Choose a CS Platform"))

    def test_rejects_article_word_top(self) -> None:
        self.assertTrue(_name_fails_quality_check("Top 10 CS Platforms"))

    def test_rejects_article_word_guide(self) -> None:
        self.assertTrue(_name_fails_quality_check("Guide to Customer Success Software"))

    def test_accepts_clean_short_name(self) -> None:
        self.assertFalse(_name_fails_quality_check("Gainsight"))

    def test_accepts_clean_name_exactly_60_chars(self) -> None:
        self.assertFalse(_name_fails_quality_check("A" * 60))

    def test_accepts_hyphenated_brand_name(self) -> None:
        # Hyphen without spaces is not a title separator
        self.assertFalse(_name_fails_quality_check("Salesmsg"))

    def test_rejects_empty_string(self) -> None:
        self.assertTrue(_name_fails_quality_check(""))


class DeriveCanonicalNameTests(unittest.TestCase):
    def _make_derive(self, meta_name: str, website: str, domain_fallback: str) -> str:
        with mock.patch(
            "scripts.enrich_vendors_deterministic.company_name_from_website",
            return_value=domain_fallback,
        ):
            return _derive_canonical_name(meta_name, website)

    def test_uses_clean_og_site_name(self) -> None:
        result = self._make_derive("Gainsight", "https://gainsight.com", "Gainsight")
        self.assertEqual(result, "Gainsight")

    def test_falls_back_to_domain_when_meta_has_pipe(self) -> None:
        result = self._make_derive("Gainsight | CS Platform", "https://gainsight.com", "Gainsight")
        self.assertEqual(result, "Gainsight")

    def test_falls_back_to_domain_when_meta_is_over_40_chars(self) -> None:
        long_name = "Gainsight Customer Success Platform Suite"  # 41 chars
        self.assertGreater(len(long_name), 40)
        result = self._make_derive(long_name, "https://gainsight.com", "Gainsight")
        self.assertEqual(result, "Gainsight")

    def test_falls_back_to_domain_when_meta_starts_with_article(self) -> None:
        result = self._make_derive("The Best CS Tool", "https://gainsight.com", "Gainsight")
        self.assertEqual(result, "Gainsight")

    def test_falls_back_to_domain_when_meta_is_empty(self) -> None:
        result = self._make_derive("", "https://outreach.io", "Outreach")
        self.assertEqual(result, "Outreach")

    def test_outreach_canonical_name(self) -> None:
        result = self._make_derive("Outreach", "https://outreach.io", "Outreach")
        self.assertEqual(result, "Outreach")


if __name__ == "__main__":
    unittest.main()
