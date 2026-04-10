"""QueryMonitor — captures query history and triggers 14-step background AI analysis."""
from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from src.monitor.models import MonitorConfig, MonitorEvent

logger = logging.getLogger(__name__)


class QueryMonitor:
    """Tracks query history and triggers background analysis for slow queries.

    Step callback fires these step_type strings in order:
      "intercepted"     — slow query detected, SQL + metrics available
      "cache"           — bool: True = cache HIT, False = cache MISS
      "intent"          — str: classified intent (e.g. "query_analysis")
      "sql_extracted"   — str: SQL used for analysis
      "dense_search"    — dict: _last_stats from retriever (dense count)
      "keyword_search"  — dict: _last_stats (keyword tokens + count)
      "rrf_fusion"      — dict: _last_stats (merged count)
      "rerank"          — list[dict]: top RAG cases with scores
      "rules"           — list[Finding]: actual rule findings
      "ab_testing"      — str: variant "A" or "B"
      "anomaly"         — AnomalyResult | None
      "rewrite"         — RewriteResult | None
      "confidence"      — dict: {rule, rag, llm, total, mode}
      "complete"        — AnalysisResponse: final result
    """

    def __init__(self, config: MonitorConfig, orchestrator: Any = None) -> None:
        self.config = config
        self._orchestrator = orchestrator
        self.history: list[MonitorEvent] = []
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="monitor")
        self._step_callback: Callable | None = None
        # Synchronisation: allows the PAS simulator to wait until the current
        # analysis completes before moving to the next operation.
        self._analysis_done = threading.Event()
        self._analysis_done.set()  # no analysis pending initially

    # ── Public API ──────────────────────────────────────────────────────────

    def set_orchestrator(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator

    def set_step_callback(self, fn: Callable) -> None:
        """Register fn(step_type: str, *args) called at each analysis step."""
        self._step_callback = fn

    def record(self, event: MonitorEvent) -> None:
        """Called by MonitoredCursor after each execute(). Records + triggers analysis."""
        self.history.append(event)
        if event.is_slow and self._orchestrator is not None:
            self._analysis_done.clear()  # mark: analysis in progress
            self._executor.submit(self._analyze_with_steps, event)
        else:
            self._emit("fast_query", event)

    def get_summary(self) -> dict:
        total = len(self.history)
        slow  = sum(1 for e in self.history if e.is_slow)
        times = [e.metrics.execution_time_ms for e in self.history]
        return {
            "total_queries": total,
            "slow_queries":  slow,
            "slow_pct":      round(slow / total * 100, 1) if total else 0.0,
            "avg_time_ms":   round(sum(times) / len(times), 1) if times else 0.0,
        }

    def wait_for_analysis(self, timeout: float = 120) -> None:
        """Block until the current background analysis finishes.

        Called by PASSimulator so it waits for the full 14-step pipeline
        to complete before moving to the next operation.
        """
        self._analysis_done.wait(timeout=timeout)

    # ── Internal ────────────────────────────────────────────────────────────

    def _emit(self, step_type: str, *args: Any) -> None:
        if self._step_callback:
            try:
                self._step_callback(step_type, *args)
            except Exception as exc:
                logger.debug("Step callback error at %s: %s", step_type, exc)

    def _analyze_with_steps(self, event: MonitorEvent) -> None:
        """Background: run full AI pipeline, emitting one callback per step."""
        try:
            # ── Step: intercepted ─────────────────────────────────────────
            self._emit("intercepted", event)
            time.sleep(0.15)

            # Build user_query that includes the SQL so RAG can match table names
            user_query = (
                f"This SQL query is slow "
                f"({event.metrics.execution_time_ms:.0f}ms): {event.sql}"
            )

            # ── Step: cache ───────────────────────────────────────────────
            # Check before process() so we can report hit/miss accurately
            cache_key = user_query + f" SQL:{event.sql}"
            cache_hit = self._orchestrator.cache.get(cache_key) is not None
            self._emit("cache", cache_hit)
            time.sleep(0.10)

            # ── Full pipeline (synchronous) ───────────────────────────────
            result = self._orchestrator.process(user_query, sql=event.sql)

            # ── Step: intent ──────────────────────────────────────────────
            intent = next(
                (s.get("result") for s in result.explanation_chain
                 if s.get("action") == "classify_intent"),
                "query_analysis",
            )
            self._emit("intent", intent)
            time.sleep(0.10)

            # ── Step: sql_extracted ───────────────────────────────────────
            sql_ext = next(
                (s.get("result") for s in result.explanation_chain
                 if s.get("action") == "sql_extracted"),
                event.sql[:120],
            )
            self._emit("sql_extracted", sql_ext)
            time.sleep(0.10)

            # ── RAG sub-steps (from retriever._last_stats) ────────────────
            rag_stats = getattr(self._orchestrator.retriever, "_last_stats", {})

            self._emit("dense_search",   rag_stats); time.sleep(0.10)
            self._emit("keyword_search", rag_stats); time.sleep(0.10)
            self._emit("rrf_fusion",     rag_stats); time.sleep(0.10)

            # ── Step: rerank (actual top cases with scores) ───────────────
            rag_cases = result.metadata.get("rag_cases", [])
            self._emit("rerank", rag_cases)
            time.sleep(0.20)

            # ── Step: rules (actual Finding objects) ──────────────────────
            self._emit("rules", result.rule_findings)
            time.sleep(0.15)

            # ── Step: a/b testing ─────────────────────────────────────────
            self._emit("ab_testing", result.metadata.get("ab_variant", "?"))
            time.sleep(0.10)

            # ── Step: anomaly detection on rolling history ────────────────
            anomaly_result = None
            try:
                if len(self.history) >= 3 and hasattr(self._orchestrator, "anomaly_detector"):
                    metrics = [
                        {"latency_ms": e.metrics.execution_time_ms}
                        for e in self.history[-10:]
                    ]
                    anomaly_result = self._orchestrator.anomaly_detector.detect(metrics)
            except Exception as exc:
                logger.debug("Anomaly detection error: %s", exc)
            self._emit("anomaly", anomaly_result)
            time.sleep(0.15)

            # ── Step: query rewrite ───────────────────────────────────────
            self._emit("rewrite", result.rewritten_sql)
            time.sleep(0.15)

            # ── Step: confidence breakdown ────────────────────────────────
            rule_score = min(0.4 * len(result.rule_findings) / 3.0, 0.4) \
                if result.rule_findings else 0.0
            rag_score = 0.0
            if rag_cases:
                rv = rag_cases[0].get("_rerank_score")
                if rv is not None:
                    rag_score = round(0.4 * (1 / (1 + math.exp(-rv))), 3)
                else:
                    dist = rag_cases[0].get("_distance", 1.0)
                    rag_score = round(0.4 * max(0.0, 1.0 - dist), 3)
            llm_score = 0.2 if result.metadata.get("mode") == "online" else 0.0
            self._emit("confidence", {
                "rule":  round(rule_score, 3),
                "rag":   round(rag_score, 3),
                "llm":   round(llm_score, 3),
                "total": result.confidence,
                "mode":  result.metadata.get("mode", "offline"),
            })
            time.sleep(0.10)

            # ── Enrich result metadata with real DB metrics ───────────────
            result.metadata["real_execution_time_ms"] = event.metrics.execution_time_ms
            result.metadata["real_rows_returned"]     = event.metrics.rows_returned
            result.metadata["explain_output"] = [
                r.model_dump() for r in event.metrics.explain_output
            ]
            result.metadata["source"] = "live_monitor"
            event.analysis = result

            # ── Step: complete ────────────────────────────────────────────
            self._emit("complete", result)

        except Exception as exc:
            logger.error("Analysis failed for query: %s", exc, exc_info=True)
        finally:
            self._analysis_done.set()  # unblock simulator

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
