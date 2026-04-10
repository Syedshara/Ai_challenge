"""Integration tests for Monitor SDK — auto-skip if MySQL is not available on port 3307.

Run: docker-compose up -d  (wait ~3 minutes for employees DB to import)
Then: pytest tests/test_monitor_integration.py -v
"""
from __future__ import annotations

import pytest


def mysql_available() -> bool:
    """Check if MySQL is reachable on port 3307 with the monitor user."""
    try:
        import mysql.connector
        cnx = mysql.connector.connect(
            host="localhost",
            port=3307,
            user="monitor",
            password="monitor_pw",
            database="employees",
            connection_timeout=3,
        )
        cnx.close()
        return True
    except Exception:
        return False


_SKIP = pytest.mark.skipif(
    not mysql_available(),
    reason="MySQL not available on localhost:3307 — run: docker-compose up -d",
)


@_SKIP
def test_monitored_connection_connects():
    from src.monitor.models import MonitorConfig
    from src.monitor.connection import MonitoredConnection

    cfg = MonitorConfig()
    conn = MonitoredConnection(config=cfg)
    assert conn._raw_conn.is_connected()
    conn.close()


@_SKIP
def test_fast_pk_lookup_is_not_slow():
    from src.monitor.models import MonitorConfig
    from src.monitor.connection import MonitoredConnection

    cfg = MonitorConfig(slow_query_threshold_ms=500.0)
    conn = MonitoredConnection(config=cfg)

    with conn.cursor() as cur:
        cur.execute("SELECT emp_no, first_name FROM employees WHERE emp_no = 10001")

    assert len(conn.monitor.history) == 1
    event = conn.monitor.history[0]
    assert event.is_slow is False
    conn.close()


@_SKIP
def test_explain_output_captured():
    from src.monitor.models import MonitorConfig
    from src.monitor.connection import MonitoredConnection

    cfg = MonitorConfig()
    conn = MonitoredConnection(config=cfg)

    with conn.cursor() as cur:
        cur.execute("SELECT emp_no, first_name FROM employees WHERE emp_no = 10001")

    event = conn.monitor.history[0]
    assert event.metrics.explain_output is not None
    conn.close()


@_SKIP
def test_full_scan_flagged_in_explain():
    from src.monitor.models import MonitorConfig
    from src.monitor.connection import MonitoredConnection

    # Very low threshold to catch any query, so we can inspect EXPLAIN
    cfg = MonitorConfig(slow_query_threshold_ms=1.0)
    conn = MonitoredConnection(config=cfg)

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM employees WHERE first_name = 'Georgi'")

    event = conn.monitor.history[0]
    if event.metrics.explain_output:
        first_row = event.metrics.explain_output[0]
        assert first_row.type == "ALL", f"Expected ALL full scan, got {first_row.type}"
    conn.close()
