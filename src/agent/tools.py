"""OpenAI tool schemas for the ReAct agent loop.

These are passed to ``openai_client.chat.completions.create(tools=TOOL_SCHEMAS)``
so the LLM can decide which tools to invoke based on the user's question.
"""
from __future__ import annotations

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "analyze_sql",
            "description": (
                "Analyze a SQL query for performance anti-patterns. "
                "Returns rule-based findings: SELECT *, missing WHERE clause, "
                "JSON_EXTRACT in WHERE, nested subqueries, missing LIMIT, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "The SQL query to analyze for performance issues",
                    }
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_cases",
            "description": (
                "Search the knowledge base for similar historical performance cases "
                "using semantic search + cross-encoder reranking. "
                "ALWAYS call this first to find similar past incidents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language description of the performance issue",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 3)",
                        "default": 3,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_anomaly",
            "description": (
                "Detect anomalies in query execution metrics using a statistical ensemble "
                "(Z-score + IQR + sliding window). Call when the user mentions latency spikes, "
                "unusual behavior, or sudden performance degradation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metrics": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of {timestamp, latency_ms} dicts",
                    }
                },
                "required": ["metrics"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rewrite_query",
            "description": (
                "Rewrite a SQL query to fix performance issues. "
                "Returns corrected SQL, list of changes made, and specific CREATE INDEX statements."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "The SQL query to rewrite",
                    }
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schema",
            "description": (
                "Get schema information for a database table. "
                "Available tables: policy_data, claims_data, config_table, audit_log."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table to look up",
                    }
                },
                "required": ["table_name"],
            },
        },
    },
]
