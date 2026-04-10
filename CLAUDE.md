# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An AI-powered SQL query performance diagnostic system for Insurance Policy Administration (PAS). It acts as an automated DBA that diagnoses slow queries, suggests fixes, and detects performance anomalies. Works in both online (with LLM) and offline (rule engine + RAG only) modes.

**Interfaces**: CLI, REST API (FastAPI), MCP Server — all delegate to a shared `AgentOrchestrator`.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run CLI (interactive Rich terminal UI)
python -m cli.main

# Run REST API (dev server)
uvicorn api.main:app --reload

# Run MCP Server (stdio for Claude Desktop)
python -m src.mcp.server

# Run MCP Server (HTTP transport)
python -m src.mcp.server --transport streamable-http --port 8001

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_rule_engine.py -v

# Run a specific test by name
pytest -k "test_detects_select_star" -v
```

## Architecture

### Core Pipeline

```
User Query
    ↓
[Intent Classifier] → determines query_analysis / optimization / anomaly_detection / system_design
    ↓
[SQL Extractor] → pulls SQL from natural language
    ↓ (3 parallel paths)
    ├─→ [Rule Engine]       — deterministic SQL anti-pattern matching
    ├─→ [RAG Retriever]     — semantic search over historical cases
    └─→ [Anomaly Detector]  — Z-score + IQR + sliding window ensemble
    ↓
[Agent Orchestrator] → ReAct loop (online) OR fixed pipeline (offline)
    ↓
[Query Rewriter] → corrected SQL + index suggestions
    ↓
AnalysisResponse → returned to CLI / REST API / MCP
```

### Key Modules

| Path | Role |
|------|------|
| `src/agent/orchestrator.py` | Central coordinator; selects online/offline mode |
| `src/agent/factory.py` | Wires all components on startup (singleton) |
| `src/agent/cache.py` | Semantic similarity cache (threshold 0.95, max 100) |
| `src/analyzer/rule_engine.py` | 10+ SQL anti-pattern detectors |
| `src/analyzer/intent.py` | Intent classification |
| `src/rag/retriever.py` | Hybrid retrieval (dense + keyword + RRF fusion) |
| `src/rag/reranker.py` | Cross-encoder reranking |
| `src/anomaly/detector.py` | 3-method ensemble; flags if ≥2 methods agree |
| `src/rewriter/rewriter.py` | SQL rewriting + `CREATE INDEX` generation |
| `src/config.py` | Pydantic `Settings` (reads `.env`), singleton `settings` |
| `src/models.py` | Pydantic data models (`AnalysisResponse`, `Finding`, etc.) |
| `api/routes.py` | FastAPI endpoints: `/health`, `/analyze/query`, `/detect/anomaly`, `/feedback` |
| `src/mcp/server.py` | MCP tools: `analyze_query`, `detect_anomaly` |
| `cli/main.py` | Rich terminal UI with 10 demo queries |

### Online vs Offline Mode

- **Online**: `LLM_API_KEY` is set → orchestrator uses ReAct agent loop with LLM
- **Offline**: No API key → deterministic pipeline (rule engine + RAG only); all tests use offline mode

### Data Layer (`data/` directory)

- `knowledge_base.json` — historical SQL cases (10+ entries) with embedding text, root cause, fixes
- `schemas.json` — table/column metadata (policy_data, claims_data, config_table, audit_log)
- `query_patterns.json` — anti-pattern definitions for the rule engine
- `metrics_history.json` — sample latency timeseries for anomaly detection tests
- `feedback_log.json` — user feedback records for the learning loop

Vector store (ChromaDB) is auto-populated from `knowledge_base.json` on first run via `factory.py`.

### LLM Provider Configuration

The system supports 7 providers configured via `.env` (see `.env.example`): Groq (recommended, free), OpenAI, Google Gemini, Anthropic Claude, DeepSeek, Ollama (local), and offline (no LLM). All providers use the OpenAI-compatible client interface.

## Testing

Tests use `pytest` with `pytest-asyncio`. Fixtures in `tests/conftest.py` load data files and construct component instances in offline mode (no LLM required). Each test module maps to one component.
