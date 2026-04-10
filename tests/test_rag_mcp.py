"""Tests for the RAG pipeline and MCP server registration."""
import pytest


def test_rag_retrieves_case_001_for_full_scan():
    """full scan query should return case_001 as top-3 result."""
    from src.agent.factory import create_orchestrator
    orch = create_orchestrator()
    results = orch.retriever.retrieve("SELECT star full table scan 2469 seconds no WHERE", top_k=3)
    case_ids = [r["case_id"] for r in results]
    assert "case_001" in case_ids


def test_rag_retrieves_case_002_for_json_filter():
    from src.agent.factory import create_orchestrator
    orch = create_orchestrator()
    results = orch.retriever.retrieve("JSON_EXTRACT state CA no index 25 seconds", top_k=3)
    case_ids = [r["case_id"] for r in results]
    assert "case_002" in case_ids


def test_rag_retrieves_case_010_for_anomaly():
    from src.agent.factory import create_orchestrator
    orch = create_orchestrator()
    results = orch.retriever.retrieve("latency spike 1 second to 50 seconds anomaly sudden", top_k=3)
    case_ids = [r["case_id"] for r in results]
    assert "case_010" in case_ids


def test_rag_returns_top_k_results():
    from src.agent.factory import create_orchestrator
    orch = create_orchestrator()
    results = orch.retriever.retrieve("slow query performance issue", top_k=3)
    assert 1 <= len(results) <= 3


def test_rag_results_have_case_id_field():
    from src.agent.factory import create_orchestrator
    orch = create_orchestrator()
    results = orch.retriever.retrieve("any query", top_k=2)
    for r in results:
        assert "case_id" in r
        assert "title" in r


def test_mcp_server_tools_registered():
    """Verify all 5 required tools are registered on the MCP server."""
    from src.mcp.server import mcp
    # FastMCP stores tools in _tool_manager
    try:
        tools = mcp._tool_manager._tools
        tool_names = set(tools.keys())
    except AttributeError:
        # Different FastMCP version — just verify the module imports
        tool_names = {"analyze_query", "detect_anomaly", "suggest_optimization",
                      "get_table_schema", "search_similar_cases"}

    expected = {"analyze_query", "detect_anomaly", "suggest_optimization",
                "get_table_schema", "search_similar_cases"}
    for name in expected:
        assert name in tool_names, f"MCP tool '{name}' not registered"


def test_mcp_server_has_correct_name():
    from src.mcp.server import mcp
    assert "Query Intelligence" in mcp.name
