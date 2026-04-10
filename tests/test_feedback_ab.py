"""Tests for the FeedbackLoop and ABTestingEngine."""
import json
import os
import tempfile
import pytest

from src.ab_testing.ab_engine import ABTestingEngine


# ── A/B Engine tests ──────────────────────────────────────────────────────────

def test_ab_variant_deterministic():
    ab = ABTestingEngine()
    query = "deterministic test query for ab engine abc123"
    variants = [ab.get_variant(query) for _ in range(10)]
    assert len(set(variants)) == 1, "Same query must always get same variant"


def test_ab_produces_both_variants():
    ab = ABTestingEngine()
    queries = [f"query number {i} for ab split test" for i in range(20)]
    variants = set(ab.get_variant(q) for q in queries)
    assert "A" in variants
    assert "B" in variants


def test_ab_conservative_suggestions_not_empty():
    ab = ABTestingEngine()
    analysis = {"is_select_star": True, "no_where": True, "no_limit": True,
                "schema_columns": ["col1", "col2"], "table": "policy_data"}
    suggestions = ab.generate_suggestions(analysis, "A")
    assert len(suggestions) > 0


def test_ab_aggressive_suggestions_not_empty():
    ab = ABTestingEngine()
    analysis = {"is_select_star": True, "no_where": True, "table_size_rows": 50000000,
                "frequency": "high", "join_count": 0, "table": "policy_data"}
    suggestions = ab.generate_suggestions(analysis, "B")
    assert len(suggestions) > 0


def test_ab_conservative_mentions_index():
    ab = ABTestingEngine()
    analysis = {"missing_index": True, "table": "policy_data", "filter_column": "status"}
    suggestions = ab.generate_suggestions(analysis, "A")
    text = " ".join(suggestions).lower()
    # Should mention some form of index or where clause
    assert any(w in text for w in ["index", "where", "limit", "select"])


def test_ab_get_results_with_empty_log():
    ab = ABTestingEngine()
    results = ab.get_results([])
    assert "variant_A" in results
    assert "variant_B" in results
    assert results["winner"] is None


def test_ab_get_results_with_feedback():
    ab = ABTestingEngine()
    log = [
        {"ab_variant": "A", "feedback": "positive"},
        {"ab_variant": "A", "feedback": "positive"},
        {"ab_variant": "B", "feedback": "negative"},
    ]
    results = ab.get_results(log)
    assert results["variant_A"]["win_rate"] == 1.0
    assert results["variant_B"]["win_rate"] == 0.0
    assert results["winner"] == "A"


# ── FeedbackLoop tests ────────────────────────────────────────────────────────

def test_feedback_loop_creates_log_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "feedback.json")
        from src.learning.feedback_loop import FeedbackLoop
        fl = FeedbackLoop(log_path, "data/knowledge_base.json")
        fl.record("test query", "case_001", "add index", "positive", "A")
        assert os.path.exists(log_path)
        log = json.loads(open(log_path).read())
        assert len(log) == 1
        assert log[0]["feedback"] == "positive"


def test_feedback_loop_appends_multiple_entries():
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "feedback.json")
        from src.learning.feedback_loop import FeedbackLoop
        fl = FeedbackLoop(log_path, "data/knowledge_base.json")
        fl.record("q1", "case_001", "fix1", "positive", "A")
        fl.record("q2", "case_002", "fix2", "negative", "B")
        fl.record("q3", None, "fix3", "skipped", "A")
        log = json.loads(open(log_path).read())
        assert len(log) == 3


def test_feedback_loop_stats_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "feedback.json")
        from src.learning.feedback_loop import FeedbackLoop
        fl = FeedbackLoop(log_path, "data/knowledge_base.json")
        stats = fl.get_stats()
        assert stats["total"] == 0
        assert stats["positive_rate"] == 0.0


def test_feedback_loop_stats_with_data():
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "feedback.json")
        from src.learning.feedback_loop import FeedbackLoop
        fl = FeedbackLoop(log_path, "data/knowledge_base.json")
        fl.record("q1", "case_001", "s1", "positive", "A")
        fl.record("q2", "case_001", "s2", "positive", "B")
        fl.record("q3", "case_002", "s3", "negative", "A")
        stats = fl.get_stats()
        assert stats["total"] == 3
        assert abs(stats["positive_rate"] - 0.667) < 0.01
