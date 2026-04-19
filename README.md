# Insurance PAS — AI-Powered SQL Performance Monitor

An AI system that acts as an automated DBA for Insurance Policy Administration Systems. It watches your database silently, catches slow queries the moment they happen, and tells you exactly what went wrong — with a rewritten query and an index suggestion ready to copy-paste.

The system works in two modes. You can ask it questions the normal way ("why is this query slow?") or you can plug it into your existing application with a two-line code change and let it watch every query automatically. No human needed in the middle.

---

## The Problem It Solves

Insurance PAS databases are enormous. A typical setup looks like this:

- `policy_data` — 50 million rows, with a JSON column storing policy attributes
- `claims_data` — 8 million rows
- `audit_log` — 200 million rows growing every day

A developer writes `SELECT * FROM policy_data` to pull a quick report. It works fine in development (small dataset). In production, it scans all 50 million rows and takes 2,469 seconds. By the time anyone notices, the application has been degraded for hours.

The standard process: a DBA eventually gets paged, runs EXPLAIN, figures out the issue, suggests a fix. That cycle takes hours or days.

This system collapses that cycle to seconds — and it doesn't wait for anyone to ask.

---

## How It Actually Works — The 14-Step Pipeline

Every query the system analyzes goes through 14 distinct steps. Each step builds on the last. The output of each step is visible in the live monitor so you can see exactly what the AI is thinking.

```
QUERY: "SELECT * FROM salaries"  (3,847ms in production)
│
├─ [01] Semantic Cache
│       Check if we've analyzed something similar before.
│       Cache uses cosine similarity (threshold 0.95) — not exact string match.
│       MISS → fresh analysis. HIT → instant response from memory.
│
├─ [02] Intent Classification
│       Keyword matching + template scoring determines what the user wants.
│       "3847ms" + SQL detected → query_analysis intent.
│       Could also route to: optimization, anomaly_detection, system_design.
│
├─ [03] SQL Extraction
│       Pulls the SQL statement from natural language if needed.
│       "This query took 3847ms: SELECT * FROM salaries" → "SELECT * FROM salaries"
│
├─ [04] Dense Vector Search (ChromaDB)
│       The query is embedded using sentence-transformers/all-MiniLM-L6-v2 (22M params, runs locally).
│       ChromaDB cosine similarity search across 16 historical cases.
│       Returns top 10 candidates with distance scores.
│
├─ [05] Keyword Search
│       Separate search using SQL token extraction.
│       Finds: "select", "from", "salaries", "slow", "where"
│       Matches 4 cases that contain these terms in their embedding text.
│       This catches cases that semantic search might rank low.
│
├─ [06] RRF Fusion (Reciprocal Rank Fusion)
│       Merges the dense results (10 candidates) and keyword results (4 candidates).
│       RRF formula: score = Σ 1/(k + rank) where k=60.
│       Result: a single ranked list of 10 merged candidates.
│       Why both? Dense search misses exact SQL keywords. Keyword search misses semantic meaning.
│       Together they get both.
│
├─ [07] Cross-Encoder Reranking
│       The merged 10 candidates are re-scored by a cross-encoder model
│       (cross-encoder/ms-marco-MiniLM-L-6-v2) that looks at the query and each
│       candidate together, not separately.
│       This is more accurate than the initial retrieval but slower — so we only
│       run it on 10 candidates, not all 16.
│       Output: top 3 with real relevance scores.
│       Result: case_011 (Full Scan on salaries) at score 4.99 — correct match.
│
├─ [08] Rule Engine
│       7 deterministic SQL anti-pattern detectors run against the query text.
│       These always run regardless of what the RAG found.
│       Detected:
│         ● NO_WHERE_CLAUSE  [critical] — full table scan, reads every row
│         ▸ SELECT_STAR      [warning]  — all columns fetched including JSON
│         ▸ NO_LIMIT         [warning]  — unbounded result set
│       These are fast (regex-based) and never wrong for what they catch.
│
├─ [09] A/B Testing
│       Every query is assigned to Variant A (conservative) or Variant B (aggressive)
│       via hash(query) % 2 — deterministic, same query always gets same variant.
│       Variant A: safe immediate fixes (add WHERE, add index, add LIMIT).
│       Variant B: architectural advice (materialized views, partitioning, caching).
│       The feedback loop tracks which variant users rate as more helpful.
│
├─ [10] Anomaly Detection
│       Runs a 3-method ensemble against the rolling query history:
│         Z-score:        Modified Z-score using MAD (robust against the spike itself).
│         IQR:            Interquartile range outlier detection.
│         Sliding window: Deviation from the preceding N-query moving average.
│       A query is flagged as an anomaly only when ≥2 of 3 methods agree.
│       Single-method agreement = false positive. Consensus = real anomaly.
│       For the first query (no history yet): skipped.
│
├─ [11] Query Rewriter
│       Applies deterministic transformations to the original SQL:
│         1. SELECT * → SELECT emp_no, salary, from_date, to_date  (from schema)
│         2. No WHERE → WHERE to_date > CURRENT_DATE               (safe filter)
│         3. No LIMIT → LIMIT 100 OFFSET 0
│       Also generates: CREATE INDEX idx_to_date ON salaries(to_date);
│       UPDATE/DELETE without WHERE: flagged as unsafe, never auto-rewritten.
│
├─ [12] Confidence Scoring
│       Calculated from three independent signals:
│         Rule score: +0.40 max (based on how many rules fired and severity)
│         RAG score:  +0.40 max (sigmoid of cross-encoder score for top match)
│         LLM boost:  +0.20 (only when online mode with an LLM reasoning step)
│       Total: 0.78 in this case (offline mode, 3 rules + strong RAG match).
│       This is not a guess — it's a formula based on concrete evidence.
│
└─ [13] Final Response + Alert
        CRITICAL · 78% · query_analysis
        Problem: Full table scan reads all 2.8M rows without filtering
        Fix: SELECT emp_no, salary FROM salaries WHERE to_date > CURRENT_DATE LIMIT 100;
        Index: CREATE INDEX idx_to_date ON salaries(to_date);
        Estimated improvement: ~95-99% faster
```

When the system is running in live monitor mode, you watch all 14 steps appear in real time on screen, one after another, as the AI works through the analysis.

---

## The Autonomous AI Agent

When an LLM API key is configured, the orchestrator switches from the fixed 14-step pipeline to a **ReAct agent loop** — a reasoning pattern where the AI decides which tools to call, calls them, reads the results, and decides what to do next.

The agent has access to 5 tools:

| Tool | What It Does |
|------|-------------|
| `search_cases` | RAG retrieval — searches historical cases for similar patterns |
| `analyze_sql` | Rule engine — runs anti-pattern detection on a SQL string |
| `detect_anomaly` | Anomaly detector — runs the 3-method ensemble on metric data |
| `rewrite_query` | Rewriter — produces corrected SQL + index suggestions |
| `get_schema` | Schema registry — returns column names and row counts for a table |

The agent receives the system prompt, the user's question, and the tool definitions. It decides autonomously which tools to call and in what order. A typical trace looks like:

```
Step 1: call search_cases("SELECT * FROM salaries slow 3847ms")
        → case_011 matched at 4.99, case_015 at 2.13, case_006 at -3.49

Step 2: call analyze_sql("SELECT * FROM salaries")
        → NO_WHERE_CLAUSE (critical), SELECT_STAR (warning), NO_LIMIT (warning)

Step 3: call rewrite_query("SELECT * FROM salaries")
        → rewritten SQL + CREATE INDEX

Step 4: produce final answer
        → synthesizes findings from all three tool calls into AnalysisResponse
```

The agent is bounded at 3 steps by default. If it hits that limit, it falls back to the fixed pipeline to ensure a response always comes back.

This is important: the system **never fails silently**. If the LLM is unavailable, the SSL cert check fails, or the API rate-limits, it falls back to offline mode. The user always gets an analysis.

---

## The RAG System — Why It's Built This Way

RAG (Retrieval-Augmented Generation) is the system's memory. Instead of asking an LLM to reason from scratch about every query, it first retrieves the most similar historical case and grounds the analysis in real precedent.

The knowledge base has 16 cases — 10 covering the standard insurance domain (policy_data, claims_data tables) and 6 added for the live demo (employees, salaries tables). Each case is a documented incident with the original query, what was wrong, why it was wrong, and what fixed it.

The retrieval is **hybrid** — two stages working together:

**Why not just vector search?**  
Vector search on SQL queries fails on exact keyword matching. If the embedding for "SELECT * FROM salaries" is close to "SELECT * FROM employees", the model might rank an irrelevant case higher than the right one.

**Why not just keyword search?**  
Keyword search misses semantic meaning. "Why is my premium history query taking forever?" has no SQL keywords to match against, but it semantically matches a full table scan case.

**Hybrid retrieval solves both:**
1. ChromaDB cosine similarity retrieves 10 semantic candidates
2. Keyword extraction runs a token-based search on the same 16 cases
3. Reciprocal Rank Fusion merges both ranked lists into one
4. A cross-encoder re-scores the top 10 with a model that reads query + candidate together

The result is that `SELECT * FROM salaries` correctly retrieves `case_011` (Full Scan on salaries, score: 4.99) rather than the wrong case it was retrieving before when only the user's generic "why is this slow?" question (without the SQL) was used as the retrieval query. That single fix — including the SQL in the retrieval query — changed retrieval accuracy from 0/5 to 5/5 on the demo queries.

---

## The Monitoring SDK — 2-Line Integration

The live monitoring capability is packaged as a drop-in replacement for `mysql.connector.connect()`. Any application that talks to MySQL can get full AI monitoring with two line changes:

```python
# Your existing application code — unchanged
cursor.execute("SELECT * FROM salaries")
results = cursor.fetchall()

# Before (no monitoring):
import mysql.connector
conn = mysql.connector.connect(host="localhost", database="employees")

# After (full AI monitoring — only these two lines change):
from src.monitor import MonitoredConnection
conn = MonitoredConnection(host="localhost", database="employees")
```

That's it. The rest of your application code is identical.

**What happens inside the SDK:**

When `cursor.execute()` is called, `MonitoredCursor` intercepts it:
1. Starts a timer
2. Runs the actual query (on the real MySQL connection)
3. Stops the timer
4. Runs `EXPLAIN` on a separate cursor (SELECT queries only, doesn't affect your result set)
5. Creates a `MonitorEvent` with the SQL, execution time, row count, and EXPLAIN output
6. Checks: is `execution_time_ms > threshold`? (default: 500ms)
7. If slow: submits background analysis to a `ThreadPoolExecutor` — non-blocking, your application continues
8. If fast: logs it quietly, no interruption

The background analysis thread fires all 14 steps and emits callbacks for each one. The TUI listens to those callbacks and updates the display in real time. Your application never blocks. A slow query running for 4 seconds will have its analysis ready about 1-2 seconds after it completes.

---

## What MCP Is and Why It's Here

MCP (Model Context Protocol) is a standard developed by Anthropic for connecting AI assistants to external tools and data sources. It's how Claude Desktop, Cursor, and other AI tools can call your code as if it were a native capability.

This system exposes 5 MCP tools:

```
analyze_query(sql, context)           → full analysis with confidence score
detect_anomaly(metrics)               → latency spike detection
suggest_optimization(sql)             → rewritten SQL + index recommendations
get_table_schema(table_name)          → columns, row counts, indexes
search_similar_cases(query, top_k)    → retrieve similar historical cases
```

**Why does this matter?**

With MCP enabled, a Claude Desktop user can say:

> "Look at this query from our production logs: SELECT * FROM policy_data WHERE JSON_EXTRACT(data, '$.state') = 'CA'. What's wrong with it and how do I fix it?"

Claude calls `analyze_query`, gets back the structured `AnalysisResponse`, and explains the findings in natural language — grounded in the actual rule engine output and RAG retrieval, not hallucinated.

The MCP server runs in two modes:
- **stdio** (for Claude Desktop): `python -m src.mcp.server`
- **HTTP** (for other clients): `python -m src.mcp.server --transport streamable-http --port 8001`

---

## Getting Started

### Prerequisites

- Python 3.12+
- Docker (only needed for the live monitoring demo)
- An LLM API key (optional — the system works fully without one)

### Setup (one time)

**Mac / Linux:**
```bash
git clone <repo-url> && cd Ai_challenge
chmod +x setup.sh start.sh
./setup.sh
```

**Windows:**
```bat
setup.bat
```

The setup script creates a virtual environment, installs all dependencies, and copies `.env.example` to `.env`.

### Running — Quick Start

The easiest way to run everything is through `start.sh` (Mac/Linux) or `start.bat` (Windows):

```bash
# Interactive query TUI (no Docker needed)
./start.sh

# Live monitoring demo — split-screen TUI with real MySQL
./start.sh --live

# Live monitoring — plain console output (no TUI)
./start.sh --live --no-tui

# REST API server
./start.sh --api
```

The `--live` flag automatically starts the Docker MySQL container, waits for the database to be ready (first run imports 4.1M rows — takes ~5 minutes), then launches the monitor.

**Windows:**
```bat
start.bat              &:: Interactive query TUI
start.bat --live       &:: Live monitoring demo (Docker)
start.bat --api        &:: REST API server
```

### Running — All Options

| What you want | Using start.sh | Using Python directly |
|--------------|----------------|----------------------|
| Interactive query TUI | `./start.sh` | `python cli/tui.py` |
| Single question | — | `python -m cli.main "Why is SELECT * slow?"` |
| Analyze specific SQL | — | `python -m cli.main --sql "SELECT * FROM salaries"` |
| Run all 10 demo cases | — | `python -m cli.main --demo` |
| Live monitor (split-screen) | `./start.sh --live` | `docker compose up -d && python demo_live.py` |
| Live monitor (console) | `./start.sh --live --no-tui` | `docker compose up -d && python demo_live.py --no-tui` |
| REST API | `./start.sh --api` | `uvicorn api.main:app --reload` |
| MCP server (Claude Desktop) | — | `python -m src.mcp.server` |
| Run all tests | — | `pytest tests/ -v` |

### LLM Configuration (Optional)

The system runs fully offline without any API key. To enable the ReAct agent loop, add one of these to your `.env`:

```bash
# Groq (free tier, recommended)
LLM_API_KEY=gsk_...
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.1-70b-versatile

# OpenAI
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini

# Local with Ollama
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.2
```


### Live Monitoring Demo

The live demo runs a simulated insurance PAS against a real MySQL database with 4.1 million rows (the MySQL Employees Sample Database, used as a stand-in for PAS data).

```bash
docker compose up -d
# First run: imports the employees database (~3 minutes)
# Subsequent starts: ~5 seconds

python demo_live.py
```

The TUI has three modes:
- **[1] Run once** — executes all 6 demo operations in sequence, shows full 14-step analysis for each, then stops. Best for evaluation.
- **[2] Continuous** — loops the operations like a real production system. The AI watches silently and fires alerts automatically.
- **[3] Manual / Chat** — type your own SQL or questions. The AI analyzes them with the full 14-step pipeline visible on screen.

Press SPACE to pause, R to restart, Q to quit.

---

## Architecture

### Components

```
src/
├── agent/
│   ├── orchestrator.py      Central coordinator. All interfaces (CLI, API, MCP, TUI) call this one method.
│   ├── factory.py           Wires all components together at startup. Singleton.
│   ├── cache.py             Semantic similarity cache. Cosine threshold 0.95, max 100 entries, FIFO eviction.
│   └── tools.py             Tool definitions for the LLM ReAct loop.
│
├── rag/
│   ├── retriever.py         Hybrid retrieval: dense + keyword + RRF + cross-encoder reranking.
│   ├── vector_store.py      ChromaDB wrapper. Auto-populates from knowledge_base.json on first run.
│   ├── embeddings.py        all-MiniLM-L6-v2 (22M params, runs locally). Singleton.
│   └── reranker.py          ms-marco-MiniLM-L-6-v2. Re-scores top 10 candidates. Singleton.
│
├── analyzer/
│   ├── rule_engine.py       7 SQL anti-pattern detectors. Deterministic, regex-based. Never wrong for what they catch.
│   ├── intent.py            Classifies queries into: query_analysis, optimization, anomaly_detection, system_design.
│   └── sql_parser.py        Extracts SQL from natural language, fingerprints for cache keys.
│
├── anomaly/
│   └── detector.py          Z-score (MAD-based) + IQR + sliding window. Consensus voting: ≥2 of 3 to flag.
│
├── rewriter/
│   ├── rewriter.py          Deterministic SQL rewriting: column expansion, safe WHERE injection, LIMIT addition.
│   └── index_suggester.py   Generates CREATE INDEX statements from WHERE/JOIN column analysis.
│
├── monitor/                 The monitoring SDK.
│   ├── connection.py        MonitoredConnection + MonitoredCursor. Drop-in for mysql.connector.
│   ├── monitor.py           QueryMonitor. Background analysis, 14-step callbacks, thread pool.
│   └── models.py            MonitorConfig, ExplainRow, QueryMetrics, MonitorEvent.
│
├── pas/
│   ├── operations.py        6 insurance PAS operations with SQL and business narrative.
│   └── simulator.py         PASSimulator. Runs operations in a loop or once, fires callbacks for TUI.
│
├── learning/
│   └── feedback_loop.py     Records user feedback → updates confidence_weight in knowledge_base.json.
│
├── ab_testing/
│   └── ab_engine.py         Conservative (Variant A) vs aggressive (Variant B) suggestions. Hash-based assignment.
│
└── mcp/
    └── server.py            MCP server. Exposes 5 tools for Claude Desktop and other MCP clients.
```

### Data Flow

```
User input (natural language or SQL)
    │
    ▼
AgentOrchestrator.process(user_query, sql)
    │
    ├─→ Cache.get(query)  ──── HIT ──→  return cached AnalysisResponse instantly
    │
    ├─→ MISS: run pipeline
    │         │
    │         ├─→ Intent classifier
    │         ├─→ SQL extractor
    │         ├─→ HybridRetriever.retrieve()
    │         │       ├─ ChromaDB vector search (dense)
    │         │       ├─ Keyword token search (sparse)
    │         │       ├─ RRF merge
    │         │       └─ Cross-encoder rerank → top 3 cases
    │         ├─→ QueryRuleEngine.analyze() → list[Finding]
    │         ├─→ AnomalyDetector.detect()  → AnomalyResult (if needed)
    │         ├─→ QueryRewriter.rewrite()   → RewriteResult
    │         └─→ ABTestingEngine.generate_suggestions()
    │
    ├─→ Cache.put(query, result)
    │
    └─→ AnalysisResponse
            ├─ problem, root_cause, suggestion[]
            ├─ confidence (0.0–1.0, computed from real evidence)
            ├─ severity (critical/high/medium/low)
            ├─ category (full_table_scan, json_filter, etc.)
            ├─ similar_cases[] (from RAG)
            ├─ rule_findings[] (from rule engine)
            ├─ rewritten_sql (rewritten query + index)
            ├─ anomaly_info (if anomaly detected)
            └─ explanation_chain[] (every step with inputs/outputs)
```

### Online vs Offline Mode

```
LLM_API_KEY set?
    │
    ├─ YES → ReAct agent loop
    │         LLM reads system prompt + user query
    │         LLM decides which tools to call
    │         Tool calls: search_cases, analyze_sql, rewrite_query, detect_anomaly, get_schema
    │         LLM synthesizes findings into final answer
    │         Falls back to fixed pipeline if LLM call fails at any step
    │
    └─ NO  → Fixed pipeline (deterministic)
              Intent → SQL extract → RAG → Rule engine → Rewrite → A/B suggestions
              No LLM, no API calls, works completely offline
              All tests run in this mode
```

---

## The Knowledge Base

16 documented cases covering real insurance PAS performance patterns:

| Case | Category | Pattern | Severity |
|------|----------|---------|---------|
| case_001 | full_table_scan | SELECT * FROM policy_data (50M rows) | Critical |
| case_002 | json_filter | JSON_EXTRACT in WHERE, no index | High |
| case_003 | complex_join | 3-table JOIN + JSON_EXTRACT | High |
| case_004 | high_frequency | Config lookup 10K times/day | Medium |
| case_005 | nested_subquery | WHERE policy_id IN (SELECT...) | Medium |
| case_006 | aggregation | GROUP BY + LEFT JOIN 50M rows | Medium |
| case_007 | logging_table | Audit log full scan (200M rows) | Critical |
| case_008 | config_lookup | Rate engine config, 50K hits/day | Low |
| case_009 | update_perf | Bulk UPDATE without index, table lock | High |
| case_010 | anomaly_spike | 1s → 50s latency spike | Critical |
| case_011 | full_table_scan | SELECT * FROM salaries (2.8M rows) | Critical |
| case_012 | unindexed_filter | WHERE first_name = ? on 300K rows | High |
| case_013 | json_filter | JSON_EXTRACT on metadata column | High |
| case_014 | complex_join | 4-table JOIN without date bounds | High |
| case_015 | nested_subquery | WHERE emp_no IN (SELECT...) | High |
| case_016 | healthy_query | PK lookup — what good looks like | Low |

Cases 001–010 cover the original challenge dataset. Cases 011–016 were added to match the actual tables in the MySQL demo database. `case_016` is intentionally the healthy pattern — the system needs to know what correct looks like, not just what wrong looks like.

---

## REST API

```
GET  /health                              System status, online/offline mode
GET  /analyze/query?q=...&sql=...         Full analysis — returns AnalysisResponse
POST /detect/anomaly                      Latency spike detection — returns AnomalyResult
GET  /suggest/optimization?sql=...        Rewrite + index suggestions
POST /feedback                            Submit helpfulness rating on an analysis
GET  /feedback/stats                      Positive rate, flagged cases
GET  /ab/results                          Variant A vs B win rates
```

Interactive docs: `http://localhost:8000/docs` (Swagger UI, auto-generated by FastAPI).

---

## Tests

```bash
pytest tests/ -v                    # all tests — no Docker, no API key needed
pytest tests/test_monitor.py -v     # monitoring SDK — 13 unit tests (mocked)
pytest tests/test_pas.py -v         # PAS simulator — 9 unit tests (mocked)
pytest tests/test_monitor_integration.py -v  # real MySQL (auto-skips if Docker not running)
```

The test suite has 81 tests. All of them run without Docker and without an API key. The integration tests skip automatically with a clear message if MySQL isn't running — they never block CI.

---

## If This Were Production

This system is built to demonstrate the core ideas cleanly. Here's what would change before putting it in front of real insurance carriers:

### The biggest gaps

**Real query interception at the database layer, not the application layer.**  
The current SDK wraps the application's DB connection. In production you'd want interception at the MySQL proxy layer (ProxySQL, or a MySQL audit plugin) so it catches queries from every application — ORMs, batch jobs, reporting tools — without requiring code changes in each one.

**A real-time stream, not one-at-a-time analysis.**  
Production PAS systems run thousands of queries per second. The current system handles them sequentially in a thread pool. At scale you need Kafka or a similar queue, with consumer workers pulling analysis jobs, and TimescaleDB or InfluxDB storing the time-series latency data for proper percentile computation.

**Tenant isolation.**  
Each insurance carrier needs its own isolated knowledge base (separate ChromaDB collection), separate feedback history, and separate anomaly baselines. The current system has one global knowledge base.

**The feedback loop needs to actually close.**  
Right now, user feedback updates confidence_weight in the JSON file and marks cases for review. In production, this feeds a retraining pipeline: cases consistently rated unhelpful get revised, the embedding model gets fine-tuned on the growing corpus of (query, correct_analysis) pairs, and the reranker gets updated on (query, good_case, bad_case) triples.

**PII in SQL queries.**  
SQL logs from insurance systems contain policy numbers, names, and claim IDs. A redaction layer needs to run before any SQL text touches the embedding model or gets stored anywhere.

**Generated SQL needs validation.**  
The query rewriter currently trusts its own output. In production, rewritten SQL goes through a parser validation step (check it's syntactically valid), a schema compatibility check (all referenced columns exist), and a read-only enforcement check (no one wants the AI accidentally writing a data-modifying query).

### What's already production-ready

The core components — the anomaly detection ensemble, the hybrid RAG retrieval with RRF, the rule engine, the offline mode, the Pydantic data models, the semantic cache — these are solid and would carry over without major changes. The hardest part of building this kind of system isn't the ML stack; it's making it reliable enough that a DBA trusts the output at 2am when something breaks.

### Infrastructure sketch for production

```
MySQL Proxy (ProxySQL)
    │  intercepts all queries
    ▼
Kafka topic: raw_queries
    │
    ├─→ Consumer 1: Query normalizer + PII redactor
    │       ↓
    │   Topic: clean_queries
    │       ↓
    ├─→ Consumer 2: Fast lane — rule engine only (< 5ms)
    │       ↓
    │   Alert if critical rule triggered
    │       ↓
    └─→ Consumer 3: Deep lane — full 14-step AI analysis
            ↓
        Results written to:
          - TimescaleDB (latency time series, anomaly history)
          - Redis (hot cache for dashboards)
          - PostgreSQL (AnalysisResponse archive, feedback history)
            ↓
        Dashboard (Grafana or custom)
        PagerDuty alerts for critical findings
        Slack notifications for anomaly spikes
```

The embedding model (22M params) runs as a sidecar per consumer worker. The cross-encoder reranker runs on the same sidecar. No GPU required — the models are small enough for CPU inference at this scale.

---

