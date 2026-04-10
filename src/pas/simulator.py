"""PASSimulator — runs insurance operations in a loop, emitting events for the TUI."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from src.pas.operations import PAS_OPERATIONS

logger = logging.getLogger(__name__)

# Pause between operations (seconds)
_INTER_OPERATION_PAUSE = 2.5

# Simulate PAS processing before query executes (seconds)
_PRE_QUERY_PAUSE = 0.8


class PASSimulator:
    """Simulates a PAS making insurance operations against a live MySQL database.

    Calls:
      on_start(op)       -- before the SQL executes (show narrative in TUI left panel)
      on_done(op, event) -- after execute() returns (show timing + EXPLAIN in TUI left panel)

    Both callbacks are called from the simulator's background thread.
    In a Textual app, wrap them with call_from_thread() for thread-safe UI updates.
    """

    def __init__(
        self,
        conn: Any,  # MonitoredConnection
        on_start: Callable[[dict], None],
        on_done: Callable[[dict, Any], None],
    ) -> None:
        self._conn = conn
        self._on_start = on_start
        self._on_done = on_done
        self._paused = False
        self._running = False

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def run_once(self) -> None:
        """Run each of the 6 operations exactly once, then return."""
        self._running = True
        for op in PAS_OPERATIONS:
            if not self._running:
                break
            while self._paused and self._running:
                time.sleep(0.3)
            try:
                self._run_operation(op, cycle=1)
            except Exception as exc:
                logger.error("PAS operation '%s' failed: %s", op["name"], exc)
            if self._running:
                time.sleep(_INTER_OPERATION_PAUSE)
        self._running = False

    def run(self) -> None:
        """Main loop — cycles through PAS_OPERATIONS indefinitely until stop()."""
        self._running = True
        cycle = 0

        while self._running:
            cycle += 1
            for op in PAS_OPERATIONS:
                if not self._running:
                    break

                # Respect pause flag
                while self._paused and self._running:
                    time.sleep(0.3)

                try:
                    self._run_operation(op, cycle)
                except Exception as exc:
                    logger.error("PAS operation '%s' failed: %s", op["name"], exc)

                # Inter-operation pause
                if self._running:
                    time.sleep(_INTER_OPERATION_PAUSE)

    def pause(self) -> None:
        """Pause the simulation loop (operations in progress complete first)."""
        self._paused = True

    def resume(self) -> None:
        """Resume a paused simulation."""
        self._paused = False

    def stop(self) -> None:
        """Stop the simulation loop."""
        self._running = False

    # ── Internal ─────────────────────────────────────────────────────────────

    def _run_operation(self, op: dict, cycle: int) -> None:
        """Execute one PAS operation: notify TUI -> run SQL -> notify TUI again."""
        # 1. Notify TUI: operation starting
        try:
            self._on_start(op)
        except Exception as exc:
            logger.debug("on_start callback error: %s", exc)

        # 2. Simulate PAS app processing time before query
        time.sleep(_PRE_QUERY_PAUSE)

        # 3. Execute SQL via MonitoredConnection (captures timing + EXPLAIN internally)
        event = None
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(op["sql"])
            # Retrieve the event that was just recorded
            if self._conn.monitor.history:
                event = self._conn.monitor.history[-1]
        except Exception as exc:
            logger.warning("SQL execution failed for '%s': %s", op["name"], exc)

        # 4. Notify TUI: operation complete with metrics
        try:
            self._on_done(op, event)
        except Exception as exc:
            logger.debug("on_done callback error: %s", exc)

        # 5. Wait for AI analysis to finish before moving to next operation.
        #    This ensures the TUI shows each query's full 14-step pipeline
        #    sequentially — no interleaving between operations.
        try:
            self._conn.monitor.wait_for_analysis(timeout=120)
        except Exception:
            pass
