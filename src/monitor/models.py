"""Pydantic models for the Query Monitor SDK."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MonitorConfig(BaseModel):
    """MySQL connection + monitoring settings."""

    host: str = "localhost"
    port: int = 3307
    user: str = "monitor"
    password: str = "monitor_pw"
    database: str = "employees"
    slow_query_threshold_ms: float = 500.0

    @classmethod
    def from_settings(cls, settings: Any) -> "MonitorConfig":
        """Build from src.config.Settings instance."""
        return cls(
            host=getattr(settings, "mysql_host", "localhost"),
            port=getattr(settings, "mysql_port", 3307),
            user=getattr(settings, "mysql_user", "monitor"),
            password=getattr(settings, "mysql_password", "monitor_pw"),
            database=getattr(settings, "mysql_database", "employees"),
            slow_query_threshold_ms=getattr(settings, "monitor_slow_threshold_ms", 500.0),
        )


class ExplainRow(BaseModel):
    """One row from MySQL EXPLAIN output."""

    select_type: str = ""
    table: str | None = None
    type: str = ""          # ALL, index, range, ref, const, eq_ref
    possible_keys: str | None = None
    key: str | None = None  # None means no index used
    key_len: str | None = None
    rows: int | None = None  # estimated rows examined
    filtered: float | None = None
    extra: str | None = None


class QueryMetrics(BaseModel):
    """Captured metrics for one SQL execution."""

    execution_time_ms: float
    rows_returned: int | None = None
    rows_estimated: int | None = None
    explain_output: list[ExplainRow] = Field(default_factory=list)


class MonitorEvent(BaseModel):
    """One intercepted SQL execution event."""

    sql: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    metrics: QueryMetrics
    is_slow: bool = False
    analysis: Any | None = None           # AnalysisResponse, populated async

    model_config = {"arbitrary_types_allowed": True}
