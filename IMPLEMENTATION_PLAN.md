# 🤖 IMPLEMENTATION_PLAN.md — Multi-Agent Execution Plan
> AI Engineering 3-Day Challenge — Insurance Query Intelligence System
> This file is the PRD for pi-messenger Crew. Agents pick tasks, reserve files, and build in parallel.

---

## Overview

We are building a **Mini AI System** for insurance SQL query performance analysis.
Full design is in `PLANNING.md`. This file breaks that design into **parallelizable
agent tasks** with clear ownership, dependencies, inputs, outputs, and acceptance criteria.

### Stack
```
Python 3.12 | ChromaDB | sentence-transformers | mcp (FastMCP) | FastAPI | OpenAI SDK | Rich | NumPy/SciPy
Install: pip install chromadb sentence-transformers mcp
```

### Repository Layout (target)
```
Ai_challenge/
├── data/                    # Agent: DataBuilder owns this entire folder
├── src/
│   ├── config.py            # Agent: Foundation
│   ├── models.py            # Agent: Foundation
│   ├── rag/                 # Agent: RAGBuilder
│   ├── agent/               # Agent: AgentCore
│   ├── analyzer/            # Agent: RuleEngine
│   ├── rewriter/            # Agent: QueryRewriter
│   ├── anomaly/             # Agent: AnomalyDetector
│   ├── learning/            # Agent: LearningAB
│   ├── ab_testing/          # Agent: LearningAB
│   └── mcp/                 # Agent: Interfaces
├── api/                     # Agent: Interfaces
├── cli/                     # Agent: Interfaces
└── tests/                   # Agent: TestSuite
```

---

## Dependency Graph

```
TASK-01 (Foundation: config + models)
    │
    ├──────────────────────────────────────┐
    ▼                                      ▼
TASK-02 (DataBuilder: JSON datasets)   [independent]
    │
    ├──────────────────┬────────────────────────────────┐
    ▼                  ▼                                ▼
TASK-03 (RAG layer) TASK-04 (RuleEngine)           TASK-05 (AnomalyDetector)
    │                  │                                │
    └──────────────────┴────────────────────────────────┘
                       │
                       ▼
               TASK-06 (AgentCore: ReAct orchestrator + cache)
                       │
               ┌───────┴────────────────┐
               ▼                        ▼
         TASK-07 (QueryRewriter)   TASK-08 (LearningAB)
               │                        │
               └───────────────────┬────┘
                                   ▼
                           TASK-09 (Interfaces: CLI + API + MCP)
                                   │
                                   ▼
                           TASK-10 (TestSuite)
```

**Parallel safe from the start**: TASK-02, TASK-05 can run immediately after TASK-01.
**Parallel safe after TASK-02**: TASK-03 and TASK-04 can run simultaneously.
**Parallel safe after TASK-06**: TASK-07 and TASK-08 can run simultaneously.

---

## Tasks

---

### TASK-01 — Foundation: Config + Pydantic Models
**Agent**: Foundation
**Depends on**: nothing — start immediately
**Owns files**:
- `src/__init__.py`
- `src/config.py`
- `src/models.py`
- `requirements.txt`
- `.env.example`
- `setup.py` (optional)

**What to build**:

`requirements.txt`:
```
chromadb>=0.5.0
sentence-transformers>=3.0.0
mcp>=1.0.0
openai>=2.0.0
fastapi>=0.115.0
uvicorn>=0.34.0
pydantic>=2.10.0
pydantic-settings>=2.7.0
numpy>=2.0.0
scipy>=1.17.0
rich>=13.0.0
click>=8.1.0
httpx>=0.28.0
python-dotenv>=1.0.0
pytest>=8.0.0
pytest-asyncio>=0.24.0
```

`src/config.py` — must expose:
```python
class Settings(BaseSettings):
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "all-MiniLM-L6-v2"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    chroma_persist_dir: str = "chroma_db"
    knowledge_base_path: str = "data/knowledge_base.json"
    schemas_path: str = "data/schemas.json"
    metrics_path: str = "data/metrics_history.json"
    patterns_path: str = "data/query_patterns.json"
    feedback_log_path: str = "data/feedback_log.json"
    cache_threshold: float = 0.95
    cache_max_size: int = 100
    rag_top_k_retrieve: int = 10
    rag_top_k_rerank: int = 3
    anomaly_zscore_threshold: float = 3.0
    anomaly_iqr_factor: float = 1.5
    anomaly_window_size: int = 5
    agent_max_steps: int = 3
    llm_available: bool = True  # auto-set based on api key presence

settings = Settings()
```

`src/models.py` — must define ALL Pydantic models used across the system:
```python
class Finding(BaseModel):
    rule: str
    severity: str  # "critical" | "high" | "medium" | "warning" | "info"
    message: str
    fix: str

class RewriteResult(BaseModel):
    original: str
    rewritten: str
    changes: list[str]
    index_suggestions: list[str]
    estimated_improvement: str
    safe_to_apply: bool = True

class AnomalyResult(BaseModel):
    anomalies_detected: bool
    anomaly_indices: list[int]
    anomaly_points: list[dict]
    severity: str
    methods_agreed: dict

class AnalysisResponse(BaseModel):
    problem: str
    root_cause: str
    suggestion: list[str]
    confidence: float
    category: str
    severity: str
    similar_cases: list[str]
    sql_analyzed: str | None = None
    rule_findings: list[Finding] = []
    anomaly_info: AnomalyResult | None = None
    rewritten_sql: RewriteResult | None = None
    explanation_chain: list[dict] = []
    metadata: dict = {}

class AnomalyRequest(BaseModel):
    metrics: list[dict]
    query_id: str | None = None

class FeedbackEntry(BaseModel):
    id: str
    timestamp: str
    query: str
    case_retrieved: str | None
    ab_variant: str
    suggestion_given: str
    feedback: str  # "positive" | "negative" | "skipped"
    user_note: str | None = None
```

**Acceptance criteria**:
- [ ] `from src.config import settings` works
- [ ] `from src.models import AnalysisResponse, Finding, RewriteResult` works
- [ ] `settings.llm_available` is `False` when `OPENAI_API_KEY` not set
- [ ] `.env.example` documents all env vars

---

### TASK-02 — DataBuilder: All JSON Datasets
**Agent**: DataBuilder
**Depends on**: TASK-01
**Owns files**:
- `data/knowledge_base.json`
- `data/schemas.json`
- `data/metrics_history.json`
- `data/query_patterns.json`
- `data/feedback_log.json` (stub — empty array `[]`)

**What to build**:

#### `data/knowledge_base.json` — 10 cases minimum

Each case MUST have ALL these fields:
```json
{
  "case_id": "case_001",
  "title": "string",
  "category": "full_table_scan | json_filter | complex_join | high_frequency | nested_subquery | aggregation | logging_table | config_lookup | update_perf | anomaly_spike",
  "query": "string — actual SQL",
  "execution_time_sec": number,
  "frequency": "low | medium | high | very_high",
  "severity": "critical | high | medium | low",
  "context": {
    "table_size_rows": number,
    "has_index": boolean,
    "has_where_clause": boolean,
    "uses_json_extract": boolean,
    "join_count": number,
    "is_select_star": boolean
  },
  "problem": "string — 1 sentence what is wrong",
  "root_cause": "string — detailed why it is wrong",
  "suggestions": ["array", "of", "specific", "fixes"],
  "tags": ["array", "of", "tags"],
  "confidence_weight": 1.0,
  "embedding_text": "string — rich text combining title + problem + root_cause + tags for embedding"
}
```

The 10 cases to implement (map to assignment cases exactly):
| case_id | Category | Query Pattern | Execution Time |
|---------|----------|--------------|----------------|
| case_001 | full_table_scan | `SELECT * FROM policy_data` | 2469s |
| case_002 | json_filter | `SELECT * FROM policy_data WHERE JSON_EXTRACT(data, '$.policy.state') = 'CA'` | 25s |
| case_003 | complex_join | `SELECT p.*, c.*, JSON_TABLE(...)` multi-join | 180s |
| case_004 | high_frequency | `SELECT * FROM config_table WHERE key = ?` 10k/day | 0.05s |
| case_005 | nested_subquery | `SELECT * FROM claims_data WHERE policy_id IN (SELECT ...)` | 45s |
| case_006 | aggregation | `SELECT state, COUNT(*) FROM policy_data JOIN claims_data ...` | 120s |
| case_007 | logging_table | `SELECT * FROM audit_log WHERE created_date > ?` | 890s |
| case_008 | config_lookup | `SELECT value FROM config WHERE key = 'rate_engine_config'` repeated | 0.02s |
| case_009 | update_perf | `UPDATE policy_data SET status = 'EXPIRED' WHERE ...` | 310s |
| case_010 | anomaly_spike | Normal query latency 1s → spiked to 50s | spike |

#### `data/schemas.json`
```json
{
  "policy_data": {
    "columns": [
      "policy_id INT PRIMARY KEY",
      "state VARCHAR(2)",
      "premium_amount DECIMAL(10,2)",
      "status VARCHAR(20)",
      "created_date DATE",
      "data JSON"
    ],
    "row_count_estimate": 50000000,
    "indexes": ["PRIMARY KEY (policy_id)"],
    "key_columns": ["policy_id", "premium_amount", "state", "status"],
    "safe_filter": "status = 'ACTIVE'"
  },
  "claims_data": {
    "columns": [
      "claim_id INT PRIMARY KEY",
      "policy_id INT",
      "claim_amount DECIMAL(10,2)",
      "claim_date DATE",
      "status VARCHAR(20)"
    ],
    "row_count_estimate": 8000000,
    "indexes": ["PRIMARY KEY (claim_id)"],
    "key_columns": ["claim_id", "policy_id", "claim_amount", "status"],
    "safe_filter": "status = 'OPEN'"
  },
  "config_table": {
    "columns": [
      "id INT PRIMARY KEY",
      "key VARCHAR(255) UNIQUE",
      "value TEXT",
      "updated_at TIMESTAMP"
    ],
    "row_count_estimate": 500,
    "indexes": ["PRIMARY KEY (id)", "UNIQUE KEY (key)"],
    "key_columns": ["id", "key", "value"],
    "safe_filter": null
  }
}
```

#### `data/metrics_history.json`
Time-series for each case that has latency data. Must include at least case_010 with a clear anomaly spike:
```json
[
  {
    "query_id": "case_010",
    "query": "SELECT policy_id, premium_amount FROM policy_data WHERE status = 'ACTIVE'",
    "metrics": [
      {"timestamp": "2025-01-01T00:00:00Z", "latency_ms": 980, "rows_scanned": 100},
      ... 20+ data points with one or two obvious spikes ...
    ]
  }
]
```
Include metrics for at least 5 cases. Make spike data obvious (3-5x normal latency at index 3 or 4).

#### `data/query_patterns.json`
Anti-pattern rules in JSON that the rule engine reads:
```json
{
  "patterns": [
    { "id": "AP001", "name": "SELECT_STAR", "regex": "SELECT\\s+\\*", "severity": "warning", "message": "..." },
    { "id": "AP002", "name": "NO_WHERE_CLAUSE", "check": "no_where", "severity": "critical", "message": "..." },
    { "id": "AP003", "name": "JSON_EXTRACT_IN_WHERE", "regex": "JSON_EXTRACT", "severity": "high", "message": "..." },
    { "id": "AP004", "name": "NESTED_SUBQUERY", "regex": "WHERE[\\s\\S]*\\(\\s*SELECT", "severity": "medium", "message": "..." },
    { "id": "AP005", "name": "NO_LIMIT", "check": "no_limit", "severity": "warning", "message": "..." },
    { "id": "AP006", "name": "CARTESIAN_JOIN", "check": "join_without_on", "severity": "critical", "message": "..." },
    { "id": "AP007", "name": "UPDATE_WITHOUT_WHERE", "check": "update_no_where", "severity": "critical", "message": "..." }
  ]
}
```

**Acceptance criteria**:
- [ ] All 10 cases present with all required fields
- [ ] `embedding_text` field is rich (50+ words combining title, problem, root_cause, tags)
- [ ] All 3 schemas present with `key_columns` and `safe_filter`
- [ ] metrics_history has case_010 with clear spike (10x normal latency)
- [ ] query_patterns has all 7 AP rules
- [ ] `feedback_log.json` exists as `[]`
- [ ] JSON validates (no syntax errors)

---

### TASK-03 — RAG Layer: Embeddings + ChromaDB + Hybrid Search + Cross-Encoder Reranking
**Agent**: RAGBuilder
**Depends on**: TASK-01, TASK-02
**Owns files**:
- `src/rag/__init__.py`
- `src/rag/embeddings.py`
- `src/rag/vector_store.py`
- `src/rag/reranker.py`
- `src/rag/retriever.py`

**What to build**:

`src/rag/embeddings.py`:
- Class `EmbeddingModel` wrapping `SentenceTransformer('all-MiniLM-L6-v2')`
- `encode(text: str) -> np.ndarray` — single text
- `encode_batch(texts: list[str]) -> list[np.ndarray]` — batch
- Singleton pattern — model loads once at startup

`src/rag/vector_store.py`:
- Class `VectorStore` wrapping ChromaDB
- `__init__(persist_dir, collection_name="cases")` — auto-creates or loads
- `populate(cases: list[dict])` — embeds `embedding_text` field and upserts all cases
- `query(query_text: str, n_results: int = 10) -> list[dict]` — returns cases with distances
- `rebuild(cases: list[dict])` — clear + repopulate (used by learning loop)
- Auto-populate on first use if collection is empty

`src/rag/reranker.py`:
- Class `CrossEncoderReranker` wrapping `CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')`
- `rerank(query: str, candidates: list[dict], top_k: int = 3) -> list[dict]`
- Scores each (query, candidate["embedding_text"]) pair
- Returns top_k sorted by score descending
- Singleton pattern — model loads once

`src/rag/retriever.py`:
- Function `extract_sql_keywords(query: str) -> list[str]` — pull table names, SQL keywords
- Function `keyword_search(keywords: list[str], cases: list[dict]) -> list[dict]` — simple contains match with rank
- Function `reciprocal_rank_fusion(*result_lists, k=60) -> list[dict]` — RRF merging
- Class `HybridRetriever`:
  - `__init__(vector_store, reranker, embedding_model, cases)`
  - `retrieve(query: str, top_k: int = 3) -> list[dict]` — full pipeline:
    1. Dense vector search (top 10)
    2. Keyword search on same cases
    3. RRF merge
    4. Cross-encoder reranking → top 3
  - Threshold filter: drop candidates with cosine distance > 0.7

**Acceptance criteria**:
- [ ] `HybridRetriever.retrieve("SELECT * FROM policy_data is slow")` returns case_001 as top result
- [ ] `HybridRetriever.retrieve("JSON_EXTRACT slow filter")` returns case_002 as top result
- [ ] `HybridRetriever.retrieve("latency spike anomaly")` returns case_010 as top result
- [ ] Cross-encoder reranker scores all candidates, returns top 3
- [ ] VectorStore auto-populates from knowledge_base.json on first run
- [ ] VectorStore persists to `chroma_db/` directory

---

### TASK-04 — RuleEngine: SQL Pattern Analysis + Intent Classification + Fingerprinting
**Agent**: RuleEngine
**Depends on**: TASK-01, TASK-02
**Owns files**:
- `src/analyzer/__init__.py`
- `src/analyzer/sql_parser.py`
- `src/analyzer/rule_engine.py`
- `src/analyzer/intent.py`

**What to build**:

`src/analyzer/sql_parser.py`:
- `extract_sql(text: str) -> str | None` — pull SQL from a natural language query
- `fingerprint(sql: str) -> str` — normalize SQL (replace literals with `?`, uppercase)
- `extract_table_names(sql: str) -> list[str]`
- `extract_where_columns(sql: str) -> list[str]`
- `extract_join_columns(sql: str) -> list[str]`
- `extract_json_path(sql: str) -> str | None`

`src/analyzer/rule_engine.py`:
- Class `QueryRuleEngine`:
  - Loads rules from `data/query_patterns.json`
  - `analyze(sql: str) -> list[Finding]`
  - Detects: SELECT_STAR, NO_WHERE, JSON_EXTRACT_IN_WHERE, NESTED_SUBQUERY, COMPLEX_JOIN_WITH_JSON, NO_LIMIT, UPDATE_WITHOUT_WHERE, CARTESIAN_JOIN
  - Returns `Finding` objects (from `src/models.py`)
  - `get_severity_score(findings: list[Finding]) -> float` — aggregate severity as 0.0-1.0

`src/analyzer/intent.py`:
- Intent templates dict (query_analysis, optimization, anomaly_detection, system_design, general)
- `classify_intent(query: str) -> str` — keyword match + embedding similarity
- Returns one of the 5 intent strings

**Acceptance criteria**:
- [ ] `rule_engine.analyze("SELECT * FROM policy_data")` returns 2 findings: SELECT_STAR + NO_WHERE
- [ ] `rule_engine.analyze("SELECT * FROM policy_data WHERE JSON_EXTRACT(data, '$.state') = 'CA'")` returns JSON_EXTRACT finding
- [ ] `fingerprint("SELECT * FROM policy_data WHERE state = 'CA' AND premium > 1200")` → `"SELECT * FROM POLICY_DATA WHERE STATE = '?' AND PREMIUM > ?"`
- [ ] `classify_intent("Why is this query slow?")` → `"query_analysis"`
- [ ] `classify_intent("Is this an anomaly?")` → `"anomaly_detection"`
- [ ] `classify_intent("How can I optimize this?")` → `"optimization"`

---

### TASK-05 — AnomalyDetector: Statistical Ensemble
**Agent**: AnomalyDetector
**Depends on**: TASK-01 (can start in parallel with TASK-03 and TASK-04)
**Owns files**:
- `src/anomaly/__init__.py`
- `src/anomaly/detector.py`

**What to build**:

`src/anomaly/detector.py`:
- `zscore_detect(values: list[float], threshold: float = 3.0) -> list[int]`
- `iqr_detect(values: list[float], factor: float = 1.5) -> list[int]`
- `sliding_window_detect(values: list[float], window: int = 5, threshold: float = 5.0) -> list[int]`
- `classify_severity(values: list[float], anomaly_indices: set) -> str` — "critical" | "high" | "medium" | "low"
- `detect_trend(values: list[float]) -> dict` — linear regression slope, returns `{"direction": "up|down|stable", "slope": float}`
- Class `AnomalyDetector`:
  - `detect(metrics: list[dict]) -> AnomalyResult`
  - Extracts `latency_ms` values
  - Runs all 3 methods
  - Consensus: flagged by ≥2 methods = anomaly
  - Also checks `rows_scanned` spikes if present
  - Returns `AnomalyResult` (from `src/models.py`)

**Acceptance criteria**:
- [ ] Given metrics with one spike (index 3, 10x normal): `detect()` flags index 3
- [ ] All 3 methods agree on obvious spike (10x)
- [ ] `zscore_detect([50, 52, 48, 5000, 51])` → `[3]`
- [ ] `iqr_detect([50, 52, 48, 5000, 51])` → `[3]`
- [ ] `classify_severity` returns "critical" for 50x spike
- [ ] No false positives on flat data `[50, 52, 49, 51, 50]`

---

### TASK-06 — AgentCore: ReAct Orchestrator + Query Cache
**Agent**: AgentCore
**Depends on**: TASK-03, TASK-04, TASK-05
**Owns files**:
- `src/agent/__init__.py`
- `src/agent/orchestrator.py`
- `src/agent/tools.py`
- `src/agent/cache.py`

**What to build**:

`src/agent/cache.py`:
- Class `QueryCache`:
  - `__init__(embedding_model, threshold=0.95, max_size=100)`
  - `get(query: str) -> AnalysisResponse | None`
  - `put(query: str, result: AnalysisResponse)`
  - `_cosine(a, b) -> float`
  - FIFO eviction when >max_size
  - Adds `cache_hit: True` to metadata when returning cached result

`src/agent/tools.py`:
- OpenAI tool schemas (JSON) for: `analyze_sql`, `search_cases`, `detect_anomaly`, `rewrite_query`, `get_schema`
- `TOOL_SCHEMAS: list[dict]` — ready to pass to `openai_client.chat.completions.create(tools=...)`

`src/agent/orchestrator.py`:
- Class `AgentOrchestrator`:
  - `__init__(retriever, rule_engine, anomaly_detector, rewriter, schema_registry, cache, settings)`
  - `process(user_query: str) -> AnalysisResponse` — main entry point for ALL interfaces (CLI, API, MCP)
  - `_agent_loop(user_query, max_steps=3) -> AnalysisResponse` — ReAct with OpenAI tool-calling
  - `_fixed_pipeline(user_query) -> AnalysisResponse` — deterministic fallback (offline)
  - `_dispatch_tool(tool_name, args) -> dict` — calls the right component
  - `_parse_response(content, tool_results) -> AnalysisResponse`
  - `_fallback_synthesis(query, tool_results) -> AnalysisResponse`
  - `calculate_confidence(rule_findings, rag_results, llm_used) -> float`
  - Agent system prompt as module-level constant `AGENT_SYSTEM_PROMPT`

The system prompt MUST be:
```
You are a senior database performance analyst for an insurance Policy Administration System (PAS).
You diagnose SQL performance issues, detect anomalies, and suggest specific fixes.

You have tools available. Use them to gather evidence before answering:
1. search_cases — ALWAYS call this first to find similar past incidents
2. analyze_sql — call this when the user provides or mentions a SQL query
3. detect_anomaly — call this when the user mentions latency spikes or unusual behavior
4. rewrite_query — call this to generate corrected SQL with index suggestions
5. get_schema — call this when you need column names or table structure

Rules:
- Base your answer on tool results, not general knowledge
- If multiple tools are relevant, call them all before answering
- Provide specific fixes (CREATE INDEX statements, rewritten SQL)
- Rate confidence: high (rule match + RAG match), medium (one source), low (general)
- Always respond as JSON: {problem, root_cause, suggestion, confidence, category, severity}
```

**Acceptance criteria**:
- [ ] `orchestrator.process("Why is SELECT * FROM policy_data slow?")` returns `AnalysisResponse`
- [ ] When `OPENAI_API_KEY` not set, falls back to fixed pipeline without error
- [ ] Cache returns hit on second identical query (processing_time much faster)
- [ ] Agent loop calls at minimum `search_cases` and `analyze_sql` for a SQL query
- [ ] Response includes `explanation_chain` with steps
- [ ] `confidence` is a float 0.0-1.0, not hardcoded

---

### TASK-07 — QueryRewriter: SQL Rewrite Engine + Index Suggestions
**Agent**: QueryRewriter
**Depends on**: TASK-01, TASK-02 (needs schemas.json)
**Owns files**:
- `src/rewriter/__init__.py`
- `src/rewriter/rewriter.py`
- `src/rewriter/index_suggester.py`

**What to build**:

`src/rewriter/index_suggester.py`:
- `suggest_indexes(sql: str, table: str, schema: dict) -> list[str]`
- Generates specific `CREATE INDEX` SQL statements from:
  - WHERE clause columns
  - JOIN columns
  - Composite indexes for multi-column WHERE
  - Generated column + index for JSON_EXTRACT

`src/rewriter/rewriter.py`:
- Class `QueryRewriter`:
  - `__init__(schema_registry: dict)` — loads from schemas.json
  - `rewrite(sql: str) -> RewriteResult`
  - Applies these rules IN ORDER:
    1. SELECT * → specific columns from schema
    2. No WHERE → inject safe filter from schema's `safe_filter` field
    3. No LIMIT → append `LIMIT 100 OFFSET 0`
    4. JSON_EXTRACT in WHERE → rewrite to use named column reference (add comment explaining generated column approach)
    5. Nested subquery → rewrite as JOIN (best effort, flag if complex)
  - UPDATE/DELETE without WHERE → set `safe_to_apply: False`, do NOT rewrite
  - `_estimate_improvement(changes: list[str]) -> str` — e.g., "~99% faster", "moderate", "significant"
  - `_get_safe_filter(table: str) -> str | None` — from schemas.json

**Acceptance criteria**:
- [ ] `rewriter.rewrite("SELECT * FROM policy_data")`:
  - `changes` includes "Replaced SELECT *" and "Added WHERE" and "Added LIMIT"
  - `rewritten` has `policy_id, premium_amount, state, status` columns
  - `rewritten` has `WHERE status = 'ACTIVE'`
  - `rewritten` has `LIMIT 100`
  - `index_suggestions` has at least one CREATE INDEX statement
- [ ] `rewriter.rewrite("UPDATE policy_data SET status = 'X'")`:
  - `safe_to_apply` is `False`
  - `rewritten` equals original (not changed)
- [ ] `rewriter.rewrite("SELECT * FROM policy_data WHERE JSON_EXTRACT(data, '$.state') = 'CA'")`:
  - `changes` includes JSON_EXTRACT note
  - `index_suggestions` includes generated column suggestion

---

### TASK-08 — LearningAB: Feedback Loop + A/B Testing Engine
**Agent**: LearningAB
**Depends on**: TASK-01, TASK-06 (needs orchestrator interface defined)
**Owns files**:
- `src/learning/__init__.py`
- `src/learning/feedback_loop.py`
- `src/ab_testing/__init__.py`
- `src/ab_testing/ab_engine.py`

**What to build**:

`src/learning/feedback_loop.py`:
- Class `FeedbackLoop`:
  - `__init__(knowledge_base_path, vector_store)` 
  - `record(query, case_id, suggestion, feedback, ab_variant, note=None)` — appends to feedback_log.json
  - `process() -> dict` — reads log, updates `confidence_weight` in knowledge_base.json, triggers `vector_store.rebuild()`, returns `{updated: list, flagged: list}`
  - `get_stats() -> dict` — returns `{total, positive_rate, cases_flagged, last_processed}`
  - Flag threshold: win_rate < 0.4 AND total >= 5

`src/ab_testing/ab_engine.py`:
- Class `ABTestingEngine`:
  - `get_variant(query: str) -> str` — `"A"` or `"B"` via `hash(query) % 2`
  - `generate_suggestions(analysis: dict, variant: str) -> list[str]`
  - `_conservative(analysis: dict) -> list[str]` — safe immediate fixes (add WHERE, add index, LIMIT)
  - `_aggressive(analysis: dict) -> list[str]` — deep architectural advice (materialized views, partitioning, caching)
  - `get_results(feedback_log: list) -> dict` — win rates per variant, winner, recommendation
  - `_stats(log: list, variant: str) -> dict` — queries, positive_feedback, win_rate

**Acceptance criteria**:
- [ ] `feedback_loop.record(...)` creates/appends to `data/feedback_log.json`
- [ ] `ab_engine.get_variant("same query")` always returns same variant (deterministic)
- [ ] `ab_engine.get_variant(queryA)` and `ab_engine.get_variant(queryB)` produce both A and B across 10 different queries
- [ ] `ab_engine.generate_suggestions(analysis, "A")` returns conservative suggestions
- [ ] `ab_engine.generate_suggestions(analysis, "B")` returns architectural suggestions
- [ ] `feedback_loop.process()` updates knowledge_base.json confidence_weight
- [ ] `feedback_loop.get_stats()` returns valid stats dict

---

### TASK-09 — Interfaces: CLI + REST API + MCP Server
**Agent**: Interfaces
**Depends on**: TASK-06, TASK-07, TASK-08
**Owns files**:
- `cli/__init__.py`
- `cli/main.py`
- `api/__init__.py`
- `api/main.py`
- `api/routes.py`
- `src/mcp/__init__.py`
- `src/mcp/server.py`

**What to build**:

#### CLI (`cli/main.py`) — Rich interactive terminal

Commands:
```bash
python cli/main.py                              # interactive REPL mode
python cli/main.py "Why is SELECT * slow?"     # one-shot query
python cli/main.py --sql "SELECT * FROM ..."   # explicit SQL
python cli/main.py --process-feedback          # trigger learning loop
python cli/main.py --feedback-stats            # show feedback statistics
python cli/main.py --ab-results                # show A/B test results
python cli/main.py --demo                      # run all 10 cases in sequence
```

Output format using Rich:
- Panel with problem (red for critical, yellow for high, green for low)
- Root cause section
- Suggestions numbered list
- Confidence progress bar `████████░░ 80%`
- Category + Severity badges
- Similar cases list
- `[y/n/s]` feedback prompt after each response
- `type 'rewrite'` to see rewritten SQL
- `type 'chain'` to see explanation chain

#### REST API (`api/main.py` + `api/routes.py`) — FastAPI

Endpoints:
```
GET  /analyze/query?q={query}&sql={sql}    → AnalysisResponse
POST /detect/anomaly                        → AnomalyResult  (body: AnomalyRequest)
GET  /suggest/optimization?sql={sql}       → AnalysisResponse
POST /feedback                             → {"status": "recorded"}
GET  /ab/results                           → AB results dict
GET  /feedback/stats                       → feedback stats
GET  /health                               → {"status": "ok", "mode": "online|offline"}
GET  /docs                                 → Swagger UI (auto, FastAPI)
```

#### MCP Server (`src/mcp/server.py`) — FastMCP (official SDK)

Tools to expose:
```python
@mcp_server.tool()
def analyze_query(sql: str, context: str = "") -> dict: ...

@mcp_server.tool()
def detect_anomaly(metrics: list[dict]) -> dict: ...

@mcp_server.tool()
def suggest_optimization(sql: str) -> dict: ...

@mcp_server.tool()
def get_table_schema(table_name: str) -> dict: ...

@mcp_server.tool()
def search_similar_cases(query: str, top_k: int = 3) -> list[dict]: ...
```

Resources:
```python
@mcp_server.resource("schema://{table_name}")
def table_schema_resource(table_name: str) -> str: ...

@mcp_server.resource("cases://all")
def all_cases_resource() -> str: ...
```

Run commands in module `__main__`:
```bash
python -m src.mcp.server                                    # stdio transport
python -m src.mcp.server --transport streamable-http --port 8001  # HTTP transport
```

**Acceptance criteria**:
- [ ] `python cli/main.py "Why is SELECT * FROM policy_data slow?"` produces Rich formatted output
- [ ] CLI feedback prompt appears after each response, records to feedback_log.json
- [ ] `uvicorn api.main:app` starts without error
- [ ] `GET /analyze/query?q=slow+query&sql=SELECT+*+FROM+policy_data` returns valid AnalysisResponse JSON
- [ ] `POST /detect/anomaly` with metrics JSON returns AnomalyResult
- [ ] `GET /health` returns `{"status": "ok", "mode": "online"}` or `"offline"`
- [ ] MCP server starts with `python -m src.mcp.server`
- [ ] All 5 MCP tools are registered and return valid dicts
- [ ] `python cli/main.py --demo` runs all 10 cases end-to-end

---

### TASK-10 — TestSuite: All Tests
**Agent**: TestSuite
**Depends on**: TASK-01 through TASK-09 (write tests as modules complete)
**Owns files**:
- `tests/__init__.py`
- `tests/test_data.py`
- `tests/test_rag.py`
- `tests/test_rule_engine.py`
- `tests/test_anomaly.py`
- `tests/test_rewriter.py`
- `tests/test_cache.py`
- `tests/test_orchestrator.py`
- `tests/test_feedback_ab.py`
- `tests/test_api.py`
- `tests/test_mcp.py`

**What to build**:

Each test file covers the acceptance criteria of its corresponding task. Key tests:

`tests/test_rag.py`:
```python
def test_retrieves_correct_case_for_full_scan():
    result = retriever.retrieve("SELECT * full table scan")
    assert result[0]["case_id"] == "case_001"

def test_reranker_improves_ordering():
    # cross-encoder should put case_002 first for JSON filter query
    result = retriever.retrieve("JSON_EXTRACT slow")
    assert result[0]["case_id"] == "case_002"
```

`tests/test_orchestrator.py`:
```python
def test_offline_mode_returns_response():
    # with no API key, fixed pipeline must work
    settings.openai_api_key = None
    response = orchestrator.process("Why is SELECT * slow?")
    assert response.problem
    assert response.confidence > 0

def test_cache_hit():
    orchestrator.process("identical query for cache test")
    resp2 = orchestrator.process("identical query for cache test")
    assert resp2.metadata.get("cache_hit") == True
```

`tests/test_api.py`:
```python
def test_analyze_query_endpoint(client):
    r = client.get("/analyze/query", params={"q": "slow query", "sql": "SELECT * FROM policy_data"})
    assert r.status_code == 200
    data = r.json()
    assert "problem" in data
    assert "confidence" in data

def test_detect_anomaly_endpoint(client):
    metrics = [{"timestamp": "...", "latency_ms": v} for v in [50,52,5000,51,49]]
    r = client.post("/detect/anomaly", json={"metrics": metrics})
    assert r.status_code == 200
    assert r.json()["anomalies_detected"] == True
```

`tests/test_mcp.py`:
```python
def test_mcp_tools_registered():
    tools = mcp_server.list_tools()
    tool_names = [t.name for t in tools]
    assert "analyze_query" in tool_names
    assert "detect_anomaly" in tool_names
    assert "suggest_optimization" in tool_names
    assert "get_table_schema" in tool_names
    assert "search_similar_cases" in tool_names
```

**Acceptance criteria**:
- [ ] `pytest tests/` passes with ≥ 80% of tests green
- [ ] All 5 task acceptance criteria lists covered by tests
- [ ] Offline mode tested (no API key)
- [ ] Cache hit tested
- [ ] API endpoints tested with FastAPI TestClient
- [ ] MCP tool registration tested

---

## File Ownership Map (for pi-messenger `reserve`)

| Agent | Reserve Path |
|-------|-------------|
| Foundation | `src/config.py`, `src/models.py`, `requirements.txt` |
| DataBuilder | `data/` |
| RAGBuilder | `src/rag/` |
| RuleEngine | `src/analyzer/` |
| AnomalyDetector | `src/anomaly/` |
| AgentCore | `src/agent/` |
| QueryRewriter | `src/rewriter/` |
| LearningAB | `src/learning/`, `src/ab_testing/` |
| Interfaces | `cli/`, `api/`, `src/mcp/` |
| TestSuite | `tests/` |

---

## Inter-Agent Contracts (What Each Agent Exports)

Agents must import ONLY from these interfaces — no circular dependencies:

```python
# AgentCore imports from:
from src.rag.retriever import HybridRetriever
from src.analyzer.rule_engine import QueryRuleEngine
from src.anomaly.detector import AnomalyDetector
from src.rewriter.rewriter import QueryRewriter
from src.models import AnalysisResponse, Finding, AnomalyResult
from src.config import settings

# Interfaces import from:
from src.agent.orchestrator import AgentOrchestrator
from src.anomaly.detector import AnomalyDetector
from src.learning.feedback_loop import FeedbackLoop
from src.ab_testing.ab_engine import ABTestingEngine
from src.models import AnalysisResponse, AnomalyRequest

# TestSuite imports from all of the above
```

---

## Parallel Execution Strategy

### Wave 1 (Start immediately — no dependencies)
```
Agent Foundation  → TASK-01
```

### Wave 2 (After TASK-01 completes)
```
Agent DataBuilder     → TASK-02
Agent AnomalyDetector → TASK-05  (only needs models.py + config.py)
```

### Wave 3 (After TASK-02 completes)
```
Agent RAGBuilder   → TASK-03
Agent RuleEngine   → TASK-04
Agent QueryRewriter → TASK-07   (needs schemas.json from DataBuilder)
```

### Wave 4 (After TASK-03 + TASK-04 + TASK-05 complete)
```
Agent AgentCore → TASK-06
```

### Wave 5 (After TASK-06 completes)
```
Agent LearningAB → TASK-08
```

### Wave 6 (After TASK-06 + TASK-07 + TASK-08 complete)
```
Agent Interfaces → TASK-09
```

### Wave 7 (After all above complete)
```
Agent TestSuite → TASK-10
```

**NOTE**: QueryRewriter (TASK-07) and LearningAB (TASK-08) can overlap with Interfaces (TASK-09) if Interfaces starts on CLI/API scaffolding first, then integrates Rewriter/LearningAB.

---

## Definition of Done

The system is complete when:

- [ ] `pip install -r requirements.txt` installs cleanly
- [ ] `python cli/main.py --demo` runs all 10 cases, no exceptions
- [ ] `uvicorn api.main:app --reload` starts, Swagger at `/docs`
- [ ] `python -m src.mcp.server` starts MCP server in stdio mode
- [ ] `pytest tests/ -v` ≥ 80% green
- [ ] Offline mode works (no API key set)
- [ ] Online mode works (API key set, agent loop fires)
- [ ] All 10 cases return correct category + severity
- [ ] Case_010 anomaly detected by ensemble
- [ ] Query rewriter outputs valid SQL for case_001 and case_002
- [ ] Feedback recorded to `data/feedback_log.json` after CLI interaction
- [ ] A/B variant deterministic for same query

---

## Notes for Agents

1. **DO NOT import from a module that hasn't been built yet** — use lazy imports or dependency injection
2. **All JSON files must be valid** — run `python -c "import json; json.load(open('data/knowledge_base.json'))"` before marking done
3. **Offline mode is not optional** — every component must work without `OPENAI_API_KEY`
4. **Use `src/models.py` types everywhere** — no raw dicts in function signatures where a Pydantic model exists
5. **No print statements in library code** — use Python `logging` module
6. **ChromaDB `chroma_db/` is gitignored** — do NOT commit it
7. **The orchestrator is the single entry point** — CLI, API, and MCP all call `orchestrator.process()`
