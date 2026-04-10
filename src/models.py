from __future__ import annotations
from pydantic import BaseModel, Field


class Finding(BaseModel):
    """A single rule-engine finding on a SQL query."""
    rule: str
    severity: str  # "critical" | "high" | "medium" | "warning" | "info"
    message: str
    fix: str


class RewriteResult(BaseModel):
    """Output of the QueryRewriter."""
    original: str
    rewritten: str
    changes: list[str] = Field(default_factory=list)
    index_suggestions: list[str] = Field(default_factory=list)
    estimated_improvement: str = "unknown"
    safe_to_apply: bool = True


class AnomalyResult(BaseModel):
    """Output of the AnomalyDetector."""
    anomalies_detected: bool
    anomaly_indices: list[int] = Field(default_factory=list)
    anomaly_points: list[dict] = Field(default_factory=list)
    severity: str = "none"  # "critical" | "high" | "medium" | "low" | "none"
    methods_agreed: dict = Field(default_factory=dict)


class AnalysisResponse(BaseModel):
    """Standard response returned by the orchestrator to all interfaces."""
    problem: str
    root_cause: str
    suggestion: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    category: str = "general"
    severity: str = "medium"
    similar_cases: list[str] = Field(default_factory=list)
    sql_analyzed: str | None = None
    rule_findings: list[Finding] = Field(default_factory=list)
    anomaly_info: AnomalyResult | None = None
    rewritten_sql: RewriteResult | None = None
    explanation_chain: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AnomalyRequest(BaseModel):
    """Request body for POST /detect/anomaly."""
    metrics: list[dict]
    query_id: str | None = None


class FeedbackEntry(BaseModel):
    """One feedback record stored in feedback_log.json."""
    id: str
    timestamp: str
    query: str
    case_retrieved: str | None = None
    ab_variant: str = "A"
    suggestion_given: str = ""
    feedback: str  # "positive" | "negative" | "skipped"
    user_note: str | None = None
