"""Unit tests for the PAS Simulator — no MySQL required."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.pas.operations import PAS_OPERATIONS
from src.pas.simulator import PASSimulator


# ── PAS_OPERATIONS ────────────────────────────────────────────────────────────

def test_pas_operations_count():
    assert len(PAS_OPERATIONS) == 6


def test_pas_operations_structure():
    for op in PAS_OPERATIONS:
        assert "id" in op
        assert "name" in op
        assert "narrative" in op
        assert "sql" in op
        assert "problematic" in op


def test_pas_operations_has_fast_lookup():
    fast_ops = [op for op in PAS_OPERATIONS if not op["problematic"]]
    assert len(fast_ops) >= 1, "Should have at least one fast (non-problematic) operation"


def test_pas_operations_has_problematic():
    slow_ops = [op for op in PAS_OPERATIONS if op["problematic"]]
    assert len(slow_ops) >= 4, "Should have at least 4 problematic operations"


def test_pas_operations_ids_unique():
    ids = [op["id"] for op in PAS_OPERATIONS]
    assert len(ids) == len(set(ids)), "Operation IDs must be unique"


def test_pas_operations_sql_non_empty():
    for op in PAS_OPERATIONS:
        assert op["sql"].strip(), f"Operation '{op['name']}' has empty SQL"


# ── PASSimulator ──────────────────────────────────────────────────────────────

def _make_mock_conn():
    """Build a minimal mock MonitoredConnection."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.execute = MagicMock()
    conn.cursor.return_value = cursor

    monitor = MagicMock()
    monitor.history = []
    conn.monitor = monitor
    return conn


def test_pas_simulator_on_start_called_before_on_done():
    """on_start must be called before on_done for the same operation."""
    conn = _make_mock_conn()
    call_order = []

    sim = PASSimulator(
        conn=conn,
        on_start=lambda op: call_order.append(("start", op["id"])),
        on_done=lambda op, ev: call_order.append(("done", op["id"])),
    )

    sim._run_operation(PAS_OPERATIONS[0], cycle=1)

    assert len(call_order) == 2
    assert call_order[0] == ("start", PAS_OPERATIONS[0]["id"])
    assert call_order[1] == ("done", PAS_OPERATIONS[0]["id"])


def test_pas_simulator_pause_resume():
    """Pause/resume flags are set correctly."""
    conn = _make_mock_conn()
    sim = PASSimulator(
        conn=conn,
        on_start=lambda op: None,
        on_done=lambda op, ev: None,
    )

    sim.pause()
    assert sim._paused is True

    sim.resume()
    assert sim._paused is False


def test_pas_simulator_stop():
    conn = _make_mock_conn()
    sim = PASSimulator(
        conn=conn,
        on_start=lambda op: None,
        on_done=lambda op, ev: None,
    )
    sim.stop()
    assert sim._running is False


def test_pas_simulator_calls_cursor_execute():
    """Simulator must call cursor.execute() with the operation SQL."""
    conn = _make_mock_conn()
    executed_sqls = []

    conn.cursor.return_value.execute = lambda sql, params=None: executed_sqls.append(sql)

    sim = PASSimulator(
        conn=conn,
        on_start=lambda op: None,
        on_done=lambda op, ev: None,
    )
    sim._run_operation(PAS_OPERATIONS[1], cycle=1)  # Policy Holder Lookup

    assert any("first_name" in sql for sql in executed_sqls)
