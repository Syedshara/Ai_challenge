"""Unit tests for the Monitor SDK — no MySQL connection required."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from src.monitor.models import (
    ExplainRow,
    MonitorConfig,
    MonitorEvent,
    QueryMetrics,
)
from src.monitor.monitor import QueryMonitor


# ── MonitorConfig ─────────────────────────────────────────────────────────────

def test_monitor_config_defaults():
    cfg = MonitorConfig()
    assert cfg.host == "localhost"
    assert cfg.port == 3307
    assert cfg.user == "monitor"
    assert cfg.database == "employees"
    assert cfg.slow_query_threshold_ms == 500.0


def test_monitor_config_from_settings():
    mock_settings = MagicMock()
    mock_settings.mysql_host = "db.internal"
    mock_settings.mysql_port = 3306
    mock_settings.mysql_user = "app"
    mock_settings.mysql_password = "secret"
    mock_settings.mysql_database = "prod"
    mock_settings.monitor_slow_threshold_ms = 1000.0

    cfg = MonitorConfig.from_settings(mock_settings)
    assert cfg.host == "db.internal"
    assert cfg.port == 3306
    assert cfg.slow_query_threshold_ms == 1000.0


# ── ExplainRow ────────────────────────────────────────────────────────────────

def test_explain_row_defaults():
    er = ExplainRow()
    assert er.type == ""
    assert er.key is None
    assert er.rows is None


def test_explain_row_full_scan():
    er = ExplainRow(
        select_type="SIMPLE",
        table="salaries",
        type="ALL",
        key=None,
        rows=2844047,
    )
    assert er.type == "ALL"
    assert er.key is None
    assert er.rows == 2844047


# ── QueryMetrics ──────────────────────────────────────────────────────────────

def test_query_metrics_basic():
    qm = QueryMetrics(execution_time_ms=1234.5)
    assert qm.execution_time_ms == 1234.5
    assert qm.rows_returned is None
    assert qm.explain_output == []


def test_query_metrics_with_explain():
    er = ExplainRow(type="ALL", table="employees", rows=300024)
    qm = QueryMetrics(
        execution_time_ms=850.0,
        rows_returned=50,
        rows_estimated=300024,
        explain_output=[er],
    )
    assert len(qm.explain_output) == 1
    assert qm.explain_output[0].rows == 300024


# ── MonitorEvent ──────────────────────────────────────────────────────────────

def test_monitor_event_defaults():
    qm = QueryMetrics(execution_time_ms=100.0)
    event = MonitorEvent(sql="SELECT 1", metrics=qm)
    assert event.is_slow is False
    assert event.analysis is None
    assert event.sql == "SELECT 1"
    assert event.timestamp  # auto-set


def test_monitor_event_slow_flag():
    qm = QueryMetrics(execution_time_ms=2500.0)
    event = MonitorEvent(sql="SELECT * FROM salaries", metrics=qm, is_slow=True)
    assert event.is_slow is True


# ── QueryMonitor ──────────────────────────────────────────────────────────────

def test_query_monitor_get_summary_empty():
    cfg = MonitorConfig()
    monitor = QueryMonitor(config=cfg)
    summary = monitor.get_summary()
    assert summary["total_queries"] == 0
    assert summary["slow_queries"] == 0
    assert summary["avg_time_ms"] == 0.0


def test_query_monitor_records_events():
    cfg = MonitorConfig()
    monitor = QueryMonitor(config=cfg)

    fast = MonitorEvent(
        sql="SELECT 1",
        metrics=QueryMetrics(execution_time_ms=5.0),
        is_slow=False,
    )
    slow = MonitorEvent(
        sql="SELECT * FROM salaries",
        metrics=QueryMetrics(execution_time_ms=3500.0),
        is_slow=True,
    )

    monitor.record(fast)   # no orchestrator -> no analysis submitted
    monitor.record(slow)

    assert len(monitor.history) == 2
    summary = monitor.get_summary()
    assert summary["total_queries"] == 2
    assert summary["slow_queries"] == 1
    assert summary["slow_pct"] == 50.0


def test_query_monitor_step_callback_fires():
    """All 14 step types must fire for a slow query with an orchestrator."""
    cfg = MonitorConfig()

    mock_orch = MagicMock()
    mock_response = MagicMock()
    mock_response.explanation_chain = [
        {"action": "classify_intent", "result": "query_analysis"},
        {"action": "sql_extracted",   "result": "SELECT * FROM salaries"},
    ]
    mock_response.rule_findings = []
    mock_response.metadata = {
        "rag_cases": [], "ab_variant": "A",
        "mode": "offline", "cache_hit": False,
    }
    mock_response.rewritten_sql = None
    mock_response.confidence = 0.4
    mock_orch.process.return_value = mock_response
    mock_orch.cache.get.return_value = None
    mock_orch.retriever._last_stats = {
        "dense_count": 5, "keyword_count": 2,
        "merged_count": 5, "filtered_count": 5,
        "keywords_used": ["select"],
    }
    # Give the monitor a real anomaly detector so it doesn't error
    from src.anomaly.detector import AnomalyDetector
    mock_orch.anomaly_detector = AnomalyDetector()

    monitor = QueryMonitor(config=cfg, orchestrator=mock_orch)

    steps_received = []
    monitor.set_step_callback(lambda step_type, *args: steps_received.append(step_type))

    slow = MonitorEvent(
        sql="SELECT * FROM employees WHERE first_name = 'Georgi'",
        metrics=QueryMetrics(execution_time_ms=900.0),
        is_slow=True,
    )
    monitor.record(slow)

    # Give background thread time to run all 14 steps
    time.sleep(2.5)
    monitor.shutdown()

    expected = [
        "intercepted", "cache", "intent", "sql_extracted",
        "dense_search", "keyword_search", "rrf_fusion", "rerank",
        "rules", "ab_testing", "anomaly", "rewrite", "confidence", "complete",
    ]
    for step in expected:
        assert step in steps_received, f"Missing step: {step}  (got: {steps_received})"


def test_query_monitor_no_analysis_for_fast_queries():
    """Fast queries must not trigger analysis even with orchestrator set."""
    cfg = MonitorConfig()
    mock_orch = MagicMock()
    monitor = QueryMonitor(config=cfg, orchestrator=mock_orch)

    fast = MonitorEvent(
        sql="SELECT emp_no FROM employees WHERE emp_no = 10001",
        metrics=QueryMetrics(execution_time_ms=2.0),
        is_slow=False,
    )
    monitor.record(fast)
    time.sleep(0.2)

    mock_orch.process.assert_not_called()


def test_query_monitor_slow_threshold_boundary():
    """is_slow flag on MonitorEvent determines whether analysis is triggered."""
    below = MonitorEvent(
        sql="SELECT 1", metrics=QueryMetrics(execution_time_ms=499.9), is_slow=False
    )
    at_threshold = MonitorEvent(
        sql="SELECT 1", metrics=QueryMetrics(execution_time_ms=500.0), is_slow=True
    )

    assert not below.is_slow
    assert at_threshold.is_slow
