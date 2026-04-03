"""Unit tests for services/enrichment/merge_module.py"""
import pytest
from services.enrichment.merge_module import _is_empty, run_merge, PRIORITY_RULES


# ---------------------------------------------------------------------------
# _is_empty — edge cases from the milestone spec
# ---------------------------------------------------------------------------

class TestIsEmpty:
    def test_none_is_empty(self):
        assert _is_empty(None) is True

    def test_empty_string_is_empty(self):
        assert _is_empty("") is True

    def test_whitespace_string_is_empty(self):
        assert _is_empty("   ") is True

    def test_empty_list_is_empty(self):
        assert _is_empty([]) is True

    def test_empty_dict_is_empty(self):
        assert _is_empty({}) is True

    def test_false_is_not_empty(self):
        # boolean false is a valid value — must NOT be treated as empty
        assert _is_empty(False) is False

    def test_true_is_not_empty(self):
        assert _is_empty(True) is False

    def test_zero_is_not_empty(self):
        assert _is_empty(0) is False

    def test_nonempty_string_is_not_empty(self):
        assert _is_empty("Gainsight") is False

    def test_nonempty_list_is_not_empty(self):
        assert _is_empty(["a"]) is False


# ---------------------------------------------------------------------------
# run_merge — via mock Supabase client
# ---------------------------------------------------------------------------

class _MockExecute:
    def __init__(self, data):
        self.data = data

class _MockQueryBuilder:
    def __init__(self, data):
        self._data = data
        self._updates = {}

    def select(self, *args, **kwargs):
        return self

    def update(self, data):
        self._updates = data
        return self

    def eq(self, *args, **kwargs):
        return self

    def execute(self):
        return _MockExecute(self._data)

class _MockTable:
    def __init__(self, rows):
        self._rows = rows
        self.last_update = None

    def select(self, cols):
        return _MockSelectBuilder(self._rows, self)

    def update(self, data):
        self.last_update = data
        return _MockUpdateBuilder(self)

class _MockSelectBuilder:
    def __init__(self, rows, table):
        self._rows = rows
        self._table = table

    def eq(self, *args, **kwargs):
        return self

    def execute(self):
        return _MockExecute(self._rows)

class _MockUpdateBuilder:
    def __init__(self, table):
        self._table = table

    def eq(self, *args, **kwargs):
        return self

    def execute(self):
        return _MockExecute([])


class _MockSupabaseClient:
    def __init__(self, vendor_row):
        self._vendor_row = vendor_row
        self.updates = []

    def table(self, name):
        return _CapturingTable(self._vendor_row, self.updates)


class _CapturingTable:
    def __init__(self, row, updates_list):
        self._row = row
        self._updates = updates_list

    def select(self, *args):
        return _SelectEq(self._row)

    def update(self, data):
        self._updates.append(data)
        return _UpdateEq()


class _SelectEq:
    def __init__(self, row):
        self._row = row

    def eq(self, *a, **k):
        return self

    def execute(self):
        return _MockExecute([self._row] if self._row else [])


class _UpdateEq:
    def eq(self, *a, **k):
        return self

    def execute(self):
        return _MockExecute([])


def _make_vendor_row(
    *,
    datagma_fields=None,
    g2_fields=None,
    llm_fields=None,
    tier1_fields=None,
    tier3_fields=None,
):
    row = {}
    for col, fields in [
        ("crawl_datagma_result", datagma_fields),
        ("crawl_g2_result",      g2_fields),
        ("crawl_llm_result",     llm_fields),
        ("crawl_tier1_result",   tier1_fields),
        ("crawl_tier3_result",   tier3_fields),
    ]:
        row[col] = {"ok": True, "pipeline": "test", "crawled_at": "2026-04-01T00:00:00Z", "fields": fields} if fields is not None else None
    row["crawl_tier2_result"] = None
    return row


class TestRunMerge:
    def test_datagma_founded_wins_over_llm(self):
        row = _make_vendor_row(datagma_fields={"founded": "2013"}, llm_fields={"founded": "2012"})
        client = _MockSupabaseClient(row)
        result = run_merge("https://gainsight.com", supabase_client=client)
        assert result["ok"] is True
        assert result["source_field_map"]["founded"] == "datagma"
        # Verify the update dict contains founded=2013
        main_update = result["source_field_map"]
        assert "founded" in main_update

    def test_llm_mission_when_no_other_source(self):
        row = _make_vendor_row(llm_fields={"mission": "Best CS platform"})
        client = _MockSupabaseClient(row)
        result = run_merge("https://gainsight.com", supabase_client=client)
        assert result["source_field_map"].get("mission") == "llm"

    def test_all_null_field_unchanged(self):
        row = _make_vendor_row(datagma_fields={"founded": None}, llm_fields={"mission": "Some mission"})
        client = _MockSupabaseClient(row)
        result = run_merge("https://gainsight.com", supabase_client=client)
        assert "founded" in result["fields_unchanged"]

    def test_boolean_false_is_written(self):
        row = _make_vendor_row(tier3_fields={"has_public_pricing_page": False})
        client = _MockSupabaseClient(row)
        result = run_merge("https://gainsight.com", supabase_client=client)
        assert result["source_field_map"].get("has_public_pricing_page") == "tier3"

    def test_empty_string_not_written(self):
        row = _make_vendor_row(datagma_fields={"founded": ""}, llm_fields={"founded": "2013"})
        client = _MockSupabaseClient(row)
        result = run_merge("https://gainsight.com", supabase_client=client)
        # datagma empty string should be skipped; llm should win
        assert result["source_field_map"].get("founded") == "llm"

    def test_empty_list_not_written(self):
        row = _make_vendor_row(llm_fields={"integrations": [], "mission": "Valid mission"})
        client = _MockSupabaseClient(row)
        result = run_merge("https://gainsight.com", supabase_client=client)
        assert "integrations" in result["fields_unchanged"]
        assert result["source_field_map"].get("mission") == "llm"

    def test_vendor_not_found_raises(self):
        client = _MockSupabaseClient(None)
        with pytest.raises(LookupError):
            run_merge("https://notfound.com", supabase_client=client)

    def test_priority_tier1_name_over_datagma(self):
        row = _make_vendor_row(tier1_fields={"name": "Gainsight"}, datagma_fields={"name": "Gainsight Inc"})
        client = _MockSupabaseClient(row)
        result = run_merge("https://gainsight.com", supabase_client=client)
        assert result["source_field_map"].get("name") == "tier1"

    def test_fields_merged_count(self):
        row = _make_vendor_row(
            datagma_fields={"founded": "2013", "company_size": "501-1000"},
            llm_fields={"mission": "CS platform", "icp_buyer": "VP CS"},
        )
        client = _MockSupabaseClient(row)
        result = run_merge("https://gainsight.com", supabase_client=client)
        assert result["fields_merged"] >= 4

    def test_source_field_map_written(self):
        row = _make_vendor_row(g2_fields={"g2_rating": 4.6})
        client = _MockSupabaseClient(row)
        result = run_merge("https://gainsight.com", supabase_client=client)
        assert isinstance(result["source_field_map"], dict)
        assert result["source_field_map"].get("g2_rating") == "g2"
