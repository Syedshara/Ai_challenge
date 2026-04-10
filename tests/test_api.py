"""Tests for the FastAPI REST API endpoints."""
import pytest


def test_health_returns_ok(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "mode" in data
    assert "version" in data


def test_analyze_query_returns_analysis_response(api_client):
    r = api_client.get("/analyze/query", params={
        "q": "Why is this query slow?",
        "sql": "SELECT * FROM policy_data",
    })
    assert r.status_code == 200
    data = r.json()
    assert "problem" in data
    assert "confidence" in data
    assert "suggestion" in data
    assert isinstance(data["suggestion"], list)


def test_analyze_query_without_sql(api_client):
    r = api_client.get("/analyze/query", params={"q": "tell me about slow queries"})
    assert r.status_code == 200
    assert "problem" in r.json()


def test_analyze_query_missing_q_returns_422(api_client):
    r = api_client.get("/analyze/query")
    assert r.status_code == 422


def test_detect_anomaly_finds_spike(api_client):
    metrics = [
        {"timestamp": f"2025-01-01T0{i}:00:00Z", "latency_ms": 1000 if i != 3 else 50000}
        for i in range(8)
    ]
    r = api_client.post("/detect/anomaly", json={"metrics": metrics})
    assert r.status_code == 200
    data = r.json()
    assert data["anomalies_detected"] is True
    assert 3 in data["anomaly_indices"]


def test_detect_anomaly_no_spike(api_client):
    metrics = [{"timestamp": f"2025-01-01T0{i}:00:00Z", "latency_ms": 50 + i} for i in range(8)]
    r = api_client.post("/detect/anomaly", json={"metrics": metrics})
    assert r.status_code == 200
    assert r.json()["anomalies_detected"] is False


def test_suggest_optimization_returns_response(api_client):
    r = api_client.get("/suggest/optimization", params={"sql": "SELECT * FROM policy_data"})
    assert r.status_code == 200
    data = r.json()
    assert "problem" in data
    assert "suggestion" in data


def test_record_feedback_positive(api_client):
    r = api_client.post("/feedback", json={
        "query": "api test query",
        "case_id": "case_001",
        "suggestion": "add index",
        "feedback": "positive",
        "ab_variant": "A",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "recorded"
    assert "id" in data


def test_feedback_stats_returns_dict(api_client):
    r = api_client.get("/feedback/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "positive_rate" in data


def test_ab_results_returns_dict(api_client):
    r = api_client.get("/ab/results")
    assert r.status_code == 200
    data = r.json()
    assert "variant_A" in data
    assert "variant_B" in data
    assert "total_queries" in data
