"""FastAPI route definitions.

All routes delegate to the shared AgentOrchestrator — no business logic here.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.models import AnalysisResponse, AnomalyRequest, AnomalyResult

logger = logging.getLogger(__name__)
router = APIRouter()

# ─── Lazy orchestrator / detector ─────────────────────────────────────────────

def _get_orchestrator():
    from src.agent.factory import create_orchestrator
    return create_orchestrator()

def _get_anomaly_detector():
    from src.anomaly.detector import AnomalyDetector
    from src.config import settings
    return AnomalyDetector(
        settings.anomaly_zscore_threshold,
        settings.anomaly_iqr_factor,
        settings.anomaly_window_size,
    )


# ─── Request/Response helpers ─────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    query: str
    case_id: str | None = None
    suggestion: str = ""
    feedback: str  # "positive" | "negative" | "skipped"
    ab_variant: str = "A"
    note: str | None = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/health")
def health():
    """Health check endpoint."""
    from src.config import settings
    return {
        "status": "ok",
        "mode": "online" if settings.llm_available else "offline",
        "version": "1.0.0",
    }


@router.get("/analyze/query", response_model=AnalysisResponse)
def analyze_query(
    q: str = Query(..., description="Natural language question"),
    sql: str | None = Query(None, description="Optional explicit SQL to analyze"),
):
    """Analyze a SQL query for performance issues.

    Uses RAG retrieval + rule engine + optional LLM reasoning.
    """
    try:
        orch = _get_orchestrator()
        return orch.process(user_query=q, sql=sql)
    except Exception as exc:
        logger.exception("analyze_query failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/detect/anomaly", response_model=AnomalyResult)
def detect_anomaly(request: AnomalyRequest):
    """Detect anomalies in query execution metrics.

    Runs Z-score + IQR + sliding-window ensemble.
    A point is flagged when ≥ 2 methods agree.
    """
    try:
        detector = _get_anomaly_detector()
        return detector.detect(request.metrics)
    except Exception as exc:
        logger.exception("detect_anomaly failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/suggest/optimization", response_model=AnalysisResponse)
def suggest_optimization(
    sql: str = Query(..., description="SQL query to optimize"),
):
    """Get optimization suggestions + rewritten SQL + CREATE INDEX statements."""
    try:
        orch = _get_orchestrator()
        return orch.process(
            user_query=f"How can I optimize this query: {sql}",
            sql=sql,
        )
    except Exception as exc:
        logger.exception("suggest_optimization failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/feedback")
def record_feedback(request: FeedbackRequest):
    """Record user feedback for the continuous learning loop."""
    try:
        from src.learning.feedback_loop import FeedbackLoop
        from src.config import settings
        fl = FeedbackLoop(settings.feedback_log_path, settings.knowledge_base_path)
        entry = fl.record(
            query=request.query,
            case_id=request.case_id,
            suggestion=request.suggestion,
            feedback=request.feedback,
            ab_variant=request.ab_variant,
            note=request.note,
        )
        return {"status": "recorded", "id": entry.id}
    except Exception as exc:
        logger.exception("record_feedback failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/feedback/stats")
def feedback_stats():
    """Return feedback statistics."""
    from src.learning.feedback_loop import FeedbackLoop
    from src.config import settings
    fl = FeedbackLoop(settings.feedback_log_path, settings.knowledge_base_path)
    return fl.get_stats()


@router.get("/ab/results")
def ab_results():
    """Return A/B testing win rates for Strategy A vs B."""
    from src.learning.feedback_loop import FeedbackLoop
    from src.ab_testing.ab_engine import ABTestingEngine
    from src.config import settings
    fl = FeedbackLoop(settings.feedback_log_path, settings.knowledge_base_path)
    log = fl._load_log()
    ab = ABTestingEngine()
    return ab.get_results(log)
