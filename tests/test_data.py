"""Tests for the JSON datasets (data layer)."""
import json
import pytest


REQUIRED_CASE_FIELDS = [
    "case_id", "title", "category", "query", "execution_time_sec",
    "frequency", "severity", "context", "problem", "root_cause",
    "suggestions", "tags", "embedding_text",
]

REQUIRED_SCHEMA_FIELDS = ["columns", "row_count_estimate", "indexes", "key_columns"]

VALID_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_FREQUENCIES = {"low", "medium", "high", "very_high"}


def test_knowledge_base_has_10_cases(knowledge_base):
    assert len(knowledge_base) >= 10, f"Expected at least 10 cases, got {len(knowledge_base)}"


def test_all_cases_have_required_fields(knowledge_base):
    for case in knowledge_base:
        for field in REQUIRED_CASE_FIELDS:
            assert field in case, f"Case {case.get('case_id')} missing field: {field}"


def test_case_ids_are_unique(knowledge_base):
    ids = [c["case_id"] for c in knowledge_base]
    assert len(ids) == len(set(ids)), "Duplicate case_ids found"


def test_embedding_texts_are_rich(knowledge_base):
    for case in knowledge_base:
        words = len(case["embedding_text"].split())
        assert words >= 20, (
            f"Case {case['case_id']} embedding_text too short: {words} words"
        )


def test_all_severities_valid(knowledge_base):
    for case in knowledge_base:
        assert case["severity"] in VALID_SEVERITIES, (
            f"Case {case['case_id']} has invalid severity: {case['severity']}"
        )


def test_schemas_have_all_required_tables(schemas):
    for table in ["policy_data", "claims_data", "config_table"]:
        assert table in schemas, f"Table '{table}' missing from schemas.json"


def test_schemas_have_required_fields(schemas):
    for table, schema in schemas.items():
        for field in REQUIRED_SCHEMA_FIELDS:
            assert field in schema, f"Table '{table}' missing schema field: {field}"
        assert isinstance(schema["key_columns"], list)
        assert len(schema["key_columns"]) > 0


def test_metrics_history_has_case_010(metrics_history):
    case10 = next((m for m in metrics_history if m["query_id"] == "case_010"), None)
    assert case10 is not None, "case_010 missing from metrics_history.json"


def test_case_010_has_obvious_spike(metrics_history):
    case10 = next(m for m in metrics_history if m["query_id"] == "case_010")
    latencies = [m["latency_ms"] for m in case10["metrics"]]
    max_lat = max(latencies)
    sorted_lats = sorted(latencies)
    median = sorted_lats[len(sorted_lats) // 2]
    assert max_lat > median * 5, (
        f"case_010 spike ({max_lat}ms) should be >5x normal ({median}ms)"
    )


def test_feedback_log_is_valid_json():
    from src.config import settings
    import json as _json
    log = _json.loads(open(settings.feedback_log_path).read())
    assert isinstance(log, list)
