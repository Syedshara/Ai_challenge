"""Real MCP Server using the official `mcp` Python SDK (FastMCP).

Run modes:
  python -m src.mcp.server                                  # stdio (for Claude Desktop)
  python -m src.mcp.server --transport streamable-http --port 8001  # HTTP

Claude Desktop config (~/.claude_desktop_config.json):
  {
    "mcpServers": {
      "query-intelligence": {
        "command": "python",
        "args": ["-m", "src.mcp.server"],
        "cwd": "/path/to/Ai_challenge"
      }
    }
  }
"""
from __future__ import annotations

import json
import sys
import os

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.utils.silence import suppress_all
suppress_all()

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Query Intelligence Server — Insurance PAS Analyzer")

# ─── Lazy singletons ─────────────────────────────────────────────────────────

_orchestrator = None
_anomaly_detector = None


def _get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        from src.agent.factory import create_orchestrator
        _orchestrator = create_orchestrator()
    return _orchestrator


def _get_detector():
    global _anomaly_detector
    if _anomaly_detector is None:
        from src.anomaly.detector import AnomalyDetector
        from src.config import settings
        _anomaly_detector = AnomalyDetector(
            settings.anomaly_zscore_threshold,
            settings.anomaly_iqr_factor,
            settings.anomaly_window_size,
        )
    return _anomaly_detector


# ─── Tools ───────────────────────────────────────────────────────────────────

@mcp.tool()
def analyze_query(sql: str, context: str = "") -> dict:
    """Analyze a SQL query for performance issues.

    Returns problem, root_cause, suggestions, confidence, and optionally rewritten SQL.

    Args:
        sql: The SQL query to analyze (e.g. SELECT * FROM policy_data)
        context: Optional natural language context about the issue
    """
    orch = _get_orchestrator()
    query = context or f"Analyze this SQL query for performance issues: {sql}"
    result = orch.process(user_query=query, sql=sql)
    return result.model_dump()


@mcp.tool()
def detect_anomaly(metrics: list[dict]) -> dict:
    """Detect anomalies in query execution metrics.

    Each metric must have 'timestamp' and 'latency_ms' fields.
    Uses Z-score + IQR + sliding-window ensemble — flags when ≥2 methods agree.

    Args:
        metrics: List of {timestamp, latency_ms, rows_scanned?} objects
    """
    detector = _get_detector()
    return detector.detect(metrics).model_dump()


@mcp.tool()
def suggest_optimization(sql: str) -> dict:
    """Get optimization suggestions for a SQL query.

    Returns rewritten SQL with specific issues fixed and CREATE INDEX statements.

    Args:
        sql: The SQL query to optimize
    """
    orch = _get_orchestrator()
    result = orch.process(
        user_query=f"How can I optimize this query for better performance: {sql}",
        sql=sql,
    )
    return result.model_dump()


@mcp.tool()
def get_table_schema(table_name: str) -> dict:
    """Get schema information for a database table.

    Available tables: policy_data, claims_data, config_table, audit_log

    Args:
        table_name: Name of the table to look up
    """
    import json as _json
    from src.config import settings
    schemas = _json.loads(open(settings.schemas_path).read())
    return schemas.get(table_name.lower(), {"error": f"Unknown table: {table_name}. Available: {list(schemas.keys())}"})


@mcp.tool()
def search_similar_cases(query: str, top_k: int = 3) -> list[dict]:
    """Find similar historical performance cases from the knowledge base.

    Uses hybrid search (dense + keyword) with cross-encoder reranking.

    Args:
        query: Natural language description of the performance issue
        top_k: Number of results to return (default: 3, max: 10)
    """
    orch = _get_orchestrator()
    return orch.retriever.retrieve(query, top_k=min(top_k, 10))



@mcp.tool()
def monitor_query(
    sql: str,
    host: str = "localhost",
    port: int = 3307,
    user: str = "monitor",
    password: str = "monitor_pw",
    database: str = "employees",
    slow_threshold_ms: float = 500.0,
) -> dict:
    """Execute SQL on a live MySQL database and auto-analyze if slow.

    Connects to MySQL, runs the query, captures real execution time + EXPLAIN,
    and triggers AI analysis if the query exceeds the slow threshold.

    Returns:
        sql, execution_time_ms, rows_returned, rows_estimated,
        explain_output, is_slow, analysis (if slow)

    Args:
        sql: SQL query to execute
        host: MySQL host (default: localhost)
        port: MySQL port (default: 3307 — matches docker-compose.yml)
        user: MySQL user (default: monitor)
        password: MySQL password
        database: Database name (default: employees)
        slow_threshold_ms: Threshold in ms to trigger analysis (default: 500)
    """
    try:
        from src.monitor.models import MonitorConfig
        from src.monitor.connection import MonitoredConnection
    except ImportError as exc:
        return {"error": f"Monitor SDK not available: {exc}"}

    config = MonitorConfig(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        slow_query_threshold_ms=slow_threshold_ms,
    )

    try:
        conn = MonitoredConnection(config=config, orchestrator=_get_orchestrator())
    except Exception as exc:
        return {"error": f"MySQL connection failed: {exc}. Run: docker-compose up -d"}

    try:
        with conn.cursor() as cur:
            cur.execute(sql)
    except Exception as exc:
        return {"error": f"Query execution failed: {exc}", "sql": sql}

    if not conn.monitor.history:
        return {"error": "No event recorded after execute", "sql": sql}

    event = conn.monitor.history[-1]
    conn.close()

    result = {
        "sql": event.sql,
        "execution_time_ms": event.metrics.execution_time_ms,
        "rows_returned": event.metrics.rows_returned,
        "rows_estimated": event.metrics.rows_estimated,
        "is_slow": event.is_slow,
        "explain_output": [r.model_dump() for r in event.metrics.explain_output],
        "analysis": None,
    }

    if event.analysis:
        result["analysis"] = {
            "problem": event.analysis.problem,
            "root_cause": event.analysis.root_cause,
            "suggestion": event.analysis.suggestion,
            "severity": event.analysis.severity,
            "confidence": event.analysis.confidence,
            "rewritten_sql": (
                event.analysis.rewritten_sql.rewritten
                if event.analysis.rewritten_sql
                else None
            ),
        }

    return result


# ─── Resources ───────────────────────────────────────────────────────────────

@mcp.resource("schema://{table_name}")
def table_schema_resource(table_name: str) -> str:
    """Table schema as a readable resource.

    URI format: schema://policy_data, schema://claims_data, etc.
    """
    import json as _json
    from src.config import settings
    schemas = _json.loads(open(settings.schemas_path).read())
    schema = schemas.get(table_name.lower(), {})
    return _json.dumps(schema, indent=2)


@mcp.resource("cases://all")
def all_cases_resource() -> str:
    """Summary of all 10 knowledge base cases."""
    import json as _json
    from src.config import settings
    cases = _json.loads(open(settings.knowledge_base_path).read())
    summaries = [
        {
            "case_id": c["case_id"],
            "title": c["title"],
            "category": c["category"],
            "severity": c["severity"],
            "execution_time_sec": c["execution_time_sec"],
        }
        for c in cases
    ]
    return _json.dumps(summaries, indent=2)


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = "stdio"
    port = 8001
    args = sys.argv[1:]
    if "--transport" in args:
        transport = args[args.index("--transport") + 1]
    if "--port" in args:
        port = int(args[args.index("--port") + 1])

    if transport == "streamable-http":
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    else:
        mcp.run()
