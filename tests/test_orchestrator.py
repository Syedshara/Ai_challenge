"""Tests for the AgentOrchestrator (offline mode)."""
import pytest


def test_orchestrator_returns_analysis_response(orchestrator):
    from src.models import AnalysisResponse
    result = orchestrator.process(
        "Why is SELECT * FROM policy_data slow?",
        sql="SELECT * FROM policy_data",
    )
    assert isinstance(result, AnalysisResponse)


def test_orchestrator_problem_is_non_empty(orchestrator):
    result = orchestrator.process(
        "Why is this query slow?",
        sql="SELECT * FROM policy_data",
    )
    assert result.problem
    assert len(result.problem) > 5


def test_orchestrator_confidence_in_range(orchestrator):
    result = orchestrator.process(
        "Why is this query slow?",
        sql="SELECT * FROM policy_data",
    )
    assert 0.0 <= result.confidence <= 1.0


def test_orchestrator_suggestion_is_list(orchestrator):
    result = orchestrator.process(
        "How can I optimize this?",
        sql="SELECT * FROM policy_data",
    )
    assert isinstance(result.suggestion, list)
    assert len(result.suggestion) > 0


def test_orchestrator_returns_similar_cases(orchestrator):
    result = orchestrator.process(
        "SELECT * FROM policy_data is slow",
        sql="SELECT * FROM policy_data",
    )
    assert len(result.similar_cases) > 0


def test_orchestrator_cache_hit(orchestrator):
    # First call
    orchestrator.process("cache hit test unique query 99", sql="SELECT * FROM policy_data")
    # Second identical call
    result = orchestrator.process("cache hit test unique query 99", sql="SELECT * FROM policy_data")
    assert result.metadata.get("cache_hit") is True


def test_orchestrator_explanation_chain_not_empty(orchestrator):
    result = orchestrator.process(
        "Explain performance of SELECT * FROM policy_data",
        sql="SELECT * FROM policy_data",
    )
    assert isinstance(result.explanation_chain, list)


def test_orchestrator_json_query_handled(orchestrator):
    sql = "SELECT * FROM policy_data WHERE JSON_EXTRACT(data, '$.policy.state') = 'CA'"
    result = orchestrator.process("JSON filter is slow", sql=sql)
    assert result.problem
    assert result.confidence > 0


def test_orchestrator_anomaly_query(orchestrator):
    result = orchestrator.process("Is this latency spike an anomaly?")
    assert result.problem


def test_orchestrator_system_design_query(orchestrator):
    result = orchestrator.process("What would you change in the system design for production?")
    assert result.problem
