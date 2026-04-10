# Phase 3 — Automated Live PAS Monitor with Real Database

> **Goal**: Transform the system from a passive "ask me about a query" tool into an
> active monitoring SDK that connects to a real MySQL database, auto-detects slow queries
> using real evidence (execution time, EXPLAIN output, row counts), and shows every
> intermediate analysis step — proving the AI makes smart decisions, not just pattern matching.
>
> **Key principle**: The AI only fires alerts when queries are **actually slow** (based on
> real timing), not when they merely **look bad** (text pattern matching). A `SELECT *`
> on a 500-row config table at 2ms is fine. A `SELECT *` on a 2.8M-row salary table at
> 3,847ms is a real problem. The current system cannot tell the difference. Phase 3 fixes that.
>
> **Demo experience**: `docker compose up -d && python demo_live.py` — a simulated
> Insurance PAS runs real SQL against real MySQL, the AI watches silently, and alerts
> appear automatically with real evidence. Zero human input. Every pipeline step visible.

---

## The Core Problem Phase 3 Solves

```
CURRENT SYSTEM (Phase 1+2) — pattern matching, no real evidence:

  SELECT * FROM config_table        → 🔴 CRITICAL (WRONG — it's 500 rows, 2ms!)
  SELECT * FROM policy_data         → 🔴 CRITICAL (lucky guess)
  SELECT ... WHERE policy_id = 123  → ⚠️ WARNING  (WRONG — it's a PK lookup, 0.4ms!)

  Problem: Same warnings for fast and slow queries. The system is guessing.


PHASE 3 — real execution + smart decisions:

  SELECT * FROM config_table        → ✅ FAST 2ms, 500 rows. No alert.
  SELECT * FROM salaries            → 🔴 CRITICAL. Real evidence: 3,847ms,
                                       EXPLAIN type=ALL, 2.8M rows, key=NONE.
  SELECT ... WHERE emp_no = 10001   → ✅ FAST 0.4ms, PK lookup. No alert.

  The AI only alerts when the query is ACTUALLY slow, backed by real numbers.
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     DEMO PAS APPLICATION                         │
│  (src/pas/simulator.py — simulates insurance business operations)│
│                                                                  │
│  monthly_report()   →  SELECT * FROM salaries                    │
│  policyholder_lookup() →  SELECT * FROM employees WHERE ...      │
│  compliance_audit() →  ... JSON_EXTRACT ...                      │
│  highvalue_report() →  4-table JOIN ...                          │
│  claims_analysis()  →  nested subquery ...                       │
│  fast_pk_lookup()   →  SELECT ... WHERE emp_no = 10001           │
└──────────┬───────────────────────────────────────────────────────┘
           │  Uses MonitoredConnection instead of mysql.connector
           │  (2-line change to add monitoring to ANY application)
           │
┌──────────▼───────────────────────────────────────────────────────┐
│                  MONITORING SDK (src/monitor/)                    │
│                                                                  │
│  MonitoredConnection  — drop-in wrapper for mysql.connector      │
│    └── MonitoredCursor.execute(sql)                              │
│           │                                                      │
│           ├─ 1. Start timer                                      │
│           ├─ 2. Execute REAL query on MySQL                      │
│           ├─ 3. Stop timer → e.g. 3,847ms                       │
│           ├─ 4. Run EXPLAIN → type=ALL, rows=2844047, key=NONE  │
│           ├─ 5. Check threshold: 3847ms > 500ms? → SLOW         │
│           │                                                      │
│           │  If SLOW → pass real metrics INTO the AI pipeline:   │
│           ├─ 6. orchestrator.process(sql, context={              │
│           │        execution_time_ms: 3847,                      │
│           │        rows_examined: 2844047,                       │
│           │        explain_type: "ALL",                          │
│           │        explain_key: None })                          │
│           │                                                      │
│           │  If FAST → log it, no alert, move on                 │
│           │                                                      │
│  QueryMonitor — coordinates background analysis                  │
│    ├── history: all queries with real metrics                    │
│    ├── alerts: only actually-slow queries                        │
│    ├── on_step callbacks: fires for each pipeline stage          │
│    └── get_summary(): stats for the monitoring session           │
└──────────┬───────────────────────────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────────────────────────┐
│              AI ANALYSIS PIPELINE (enhanced)                      │
│                                                                  │
│  orchestrator.process(sql, context={real metrics})                │
│    │                                                             │
│    ├─ Step 1: Intent classification                              │
│    ├─ Step 2: SQL extraction                                     │
│    ├─ Step 3: Rule engine (context-aware — uses real metrics     │
│    │          to suppress false positives on fast queries)        │
│    ├─ Step 4: RAG retrieval (query includes real timing)         │
│    ├─ Step 5: Query rewriter                                     │
│    ├─ Step 6: Confidence calculation (boosted by real evidence)  │
│    └─ Result: AnalysisResponse with real metrics embedded        │
└──────────┬───────────────────────────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────────────────────────┐
│                     MySQL (Docker)                                │
│  employees (300K) · salaries (2.8M) · titles (443K)              │
│  dept_emp (331K) · departments (9) · metadata JSON (added)       │
│  Some indexes intentionally missing → bad queries genuinely slow │
└──────────────────────────────────────────────────────────────────┘
```

### SDK Integration Story — 2-line change for any PAS system

```python
# === Before: Any PAS system's existing code ===
import mysql.connector
conn = mysql.connector.connect(host="localhost", database="employees")
cursor = conn.cursor()
cursor.execute("SELECT * FROM salaries")        # runs, nobody knows it's slow
results = cursor.fetchall()

# === After: Change 2 lines — full AI monitoring enabled ===
from src.monitor import MonitoredConnection                          # ← line 1 changed
conn = MonitoredConnection(host="localhost", database="employees")   # ← line 2 changed
cursor = conn.cursor()
cursor.execute("SELECT * FROM salaries")        # SAME code, now auto-monitored
results = cursor.fetchall()                     # SDK already captured: 3847ms, EXPLAIN ALL
# Alert was generated automatically in the background. Zero code change elsewhere.
```

---

## M1 — MySQL via Docker + Employees Database

### Why Employees Sample Database

The [MySQL Employees Sample Database](https://github.com/datacharmer/test_db) (CC-BY-SA):
- **4.1M rows** across 6 tables — large enough for genuinely slow queries
- **2.8M salary records** — `SELECT * FROM salaries` takes real seconds
- **No index on `first_name`** — unindexed filter demo built-in
- **Foreign keys** — multi-table JOIN demo
- Free, public, MySQL-native, no licensing issues

### Insurance domain narrative

The demo PAS reframes the database with insurance terminology in its operation
descriptions. The underlying data is real — only the business context is narrated:

| Employees table | PAS narrative in demo |
|----------------|----------------------|
| `employees` (300K) | Policyholder records |
| `salaries` (2.8M) | Premium payment history |
| `dept_emp` (331K) | Policy-department assignments |
| `departments` (9) | Business line configuration |
| `titles` (443K) | Coverage type records |
| `metadata` JSON (added) | Policy JSON attributes |

### Docker setup

**`docker-compose.yml`** (project root):
```yaml
services:
  mysql:
    image: mysql:8.0
    container_name: query_monitor_mysql
    environment:
      MYSQL_ROOT_PASSWORD: monitor_root_pw
      MYSQL_DATABASE: employees
      MYSQL_USER: monitor
      MYSQL_PASSWORD: monitor_pw
    ports:
      - "3307:3306"           # non-default port — won't clash with local MySQL
    volumes:
      - mysql_data:/var/lib/mysql
      - ./docker/initdb:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 5s
      timeout: 5s
      retries: 30
    command: >
      --max-allowed-packet=256M
      --innodb-buffer-pool-size=512M
      --slow-query-log=ON
      --long-query-time=0.5

volumes:
  mysql_data:
```

**`docker/initdb/01_download_employees.sh`**:
- Downloads employees sample DB from GitHub
- Imports via `mysql` CLI inside container
- Runs automatically on first `docker compose up`

**`docker/initdb/02_post_setup.sql`**:
- Adds `metadata JSON` column to `employees` table (for JSON_EXTRACT demo)
- Populates JSON from existing data (department, hire_year, gender_code)
- Drops non-essential secondary indexes (ensures bad queries are genuinely slow)
- Grants `monitor` user SELECT + EXPLAIN privileges

---

## M2 — Query Monitor SDK (`src/monitor/`)

The core SDK — wraps any MySQL connection, intercepts every query, captures real
metrics, and auto-triggers AI analysis on slow queries.

### File structure

```
src/monitor/
├── __init__.py        # exports: MonitoredConnection, QueryMonitor,
│                      #          MonitorConfig, MonitorEvent
├── models.py          # MonitorConfig, ExplainRow, QueryMetrics, MonitorEvent
├── connection.py      # MonitoredConnection + MonitoredCursor
└── monitor.py         # QueryMonitor (background analysis, step callbacks)
```

### `src/monitor/models.py`

```python
class MonitorConfig(BaseModel):
    """Configuration for the monitoring SDK."""
    host: str = "localhost"
    port: int = 3307
    user: str = "monitor"
    password: str = "monitor_pw"
    database: str = "employees"
    slow_query_threshold_ms: float = 500.0
    auto_explain: bool = True

    @classmethod
    def from_settings(cls, settings) -> "MonitorConfig":
        """Build config from the global Settings object."""
        return cls(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            slow_query_threshold_ms=settings.monitor_slow_threshold_ms,
            auto_explain=settings.monitor_auto_explain,
        )

class ExplainRow(BaseModel):
    """One row from MySQL EXPLAIN output."""
    id: int | None = None
    select_type: str = ""
    table: str | None = None
    type: str = ""            # ALL, index, range, ref, eq_ref, const
    possible_keys: str | None = None
    key: str | None = None    # actual index used (None = no index)
    rows: int | None = None   # estimated rows examined
    filtered: float | None = None
    extra: str | None = None

class QueryMetrics(BaseModel):
    """Real execution metrics captured by MonitoredCursor."""
    execution_time_ms: float
    rows_examined: int | None = None
    rows_returned: int | None = None
    explain_output: list[ExplainRow] = []

class MonitorEvent(BaseModel):
    """A single monitored query event."""
    sql: str
    timestamp: str
    metrics: QueryMetrics
    is_slow: bool = False
    analysis: AnalysisResponse | None = None   # populated async by QueryMonitor
```

### `src/monitor/connection.py` — MonitoredConnection + MonitoredCursor

```python
class MonitoredCursor:
    """Wraps mysql.connector cursor — intercepts execute(), captures metrics."""

    def execute(self, sql, params=None):
        # 1. Time the real execution
        start = time.perf_counter()
        self._cursor.execute(sql, params)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # 2. Run EXPLAIN on SELECT queries (separate cursor, does not affect results)
        explain_rows = []
        if self._config.auto_explain and sql.strip().upper().startswith("SELECT"):
            try:
                explain_cursor = self._raw_conn.cursor(dictionary=True)
                explain_cursor.execute(f"EXPLAIN {sql}")
                explain_rows = [ExplainRow(**row) for row in explain_cursor.fetchall()]
                explain_cursor.close()
            except Exception:
                pass

        # 3. Build metrics + event
        rows_examined = sum(r.rows or 0 for r in explain_rows)
        metrics = QueryMetrics(
            execution_time_ms=elapsed_ms,
            rows_examined=rows_examined,
            explain_output=explain_rows,
        )
        event = MonitorEvent(
            sql=sql, timestamp=datetime.now().isoformat(),
            metrics=metrics,
            is_slow=(elapsed_ms > self._config.slow_query_threshold_ms),
        )

        # 4. Notify monitor (if slow → background analysis)
        self._monitor.on_query(event)

    # Delegates: fetchall, fetchone, fetchmany, description, rowcount,
    #            close, __iter__, __enter__, __exit__ → real cursor


class MonitoredConnection:
    """Drop-in wrapper for mysql.connector.connect() with auto-monitoring."""

    def __init__(self, config: MonitorConfig | None = None, orchestrator=None, **kwargs):
        self._config = config or MonitorConfig(**kwargs)
        self._connection = mysql.connector.connect(
            host=self._config.host, port=self._config.port,
            user=self._config.user, password=self._config.password,
            database=self._config.database,
        )
        self._monitor = QueryMonitor(self._config, self._connection, orchestrator)

    def cursor(self, **kwargs) -> MonitoredCursor:
        real_cursor = self._connection.cursor(**kwargs)
        return MonitoredCursor(real_cursor, self._connection, self._monitor, self._config)

    @property
    def monitor(self) -> QueryMonitor:
        return self._monitor

    # Delegates: close, commit, rollback → real connection
```

### `src/monitor/monitor.py` — QueryMonitor with step callbacks

```python
class QueryMonitor:
    """Background analysis coordinator with step-by-step progress callbacks."""

    def __init__(self, config, raw_connection, orchestrator=None):
        self.config = config
        self.history: list[MonitorEvent] = []      # ALL queries
        self._raw_conn = raw_connection
        self._orchestrator = orchestrator
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._on_step: Callable | None = None      # step callback for UI

    def on_query(self, event: MonitorEvent):
        """Called by MonitoredCursor for every query."""
        self.history.append(event)
        if event.is_slow:
            self._executor.submit(self._analyze_with_steps, event)
        else:
            self._emit_step("fast_query", event)

    def _analyze_with_steps(self, event: MonitorEvent):
        """Run AI analysis on a slow query, emitting steps as they happen."""
        if not self._orchestrator:
            from src.agent.factory import create_orchestrator
            self._orchestrator = create_orchestrator()

        # Step: intercepted
        self._emit_step("intercepted", event)

        # Step: EXPLAIN details
        self._emit_step("explain", event.metrics)

        # Build context dict with real metrics for the AI pipeline
        context = {
            "execution_time_ms": event.metrics.execution_time_ms,
            "rows_examined": event.metrics.rows_examined,
            "rows_returned": event.metrics.rows_returned,
            "explain_type": event.metrics.explain_output[0].type if event.metrics.explain_output else None,
            "explain_key": event.metrics.explain_output[0].key if event.metrics.explain_output else None,
            "explain_rows": event.metrics.explain_output[0].rows if event.metrics.explain_output else None,
            "source": "live_monitor",
        }

        # Step: AI pipeline (orchestrator.process handles sub-steps)
        self._emit_step("analyzing")
        result = self._orchestrator.process(
            user_query=f"This query took {event.metrics.execution_time_ms:.0f}ms "
                       f"and examined {event.metrics.rows_examined or 'unknown'} rows. "
                       f"Why is it slow?",
            sql=event.sql,
            context=context,           # ← real metrics fed INTO the pipeline
        )

        # Walk explanation_chain to emit each sub-step
        for step in result.explanation_chain:
            self._emit_step("chain_step", step)

        # Enrich result metadata with full real metrics
        result.metadata["real_execution_time_ms"] = event.metrics.execution_time_ms
        result.metadata["real_rows_examined"] = event.metrics.rows_examined
        result.metadata["real_rows_returned"] = event.metrics.rows_returned
        result.metadata["explain_output"] = [r.model_dump() for r in event.metrics.explain_output]
        result.metadata["source"] = "live_monitor"

        event.analysis = result
        self._emit_step("complete", event)

    def _emit_step(self, step_type: str, *args):
        """Fire the step callback if registered."""
        if self._on_step:
            self._on_step(step_type, *args)

    def set_step_callback(self, fn: Callable):
        """Register a callback for step-by-step progress updates."""
        self._on_step = fn

    def get_summary(self) -> dict:
        """Return monitoring session statistics."""
        total = len(self.history)
        slow = [e for e in self.history if e.is_slow]
        fast = [e for e in self.history if not e.is_slow]
        return {
            "total_queries": total,
            "slow_queries": len(slow),
            "fast_queries": len(fast),
            "slow_pct": round(len(slow) / total * 100, 1) if total else 0,
            "avg_time_ms": round(sum(e.metrics.execution_time_ms for e in self.history) / total, 1) if total else 0,
            "slowest_query": max(self.history, key=lambda e: e.metrics.execution_time_ms).sql if self.history else None,
            "slowest_time_ms": max(e.metrics.execution_time_ms for e in self.history) if self.history else 0,
            "alerts_generated": sum(1 for e in slow if e.analysis is not None),
        }
```

---

## M3 — Context-Aware AI Pipeline (the key intelligence upgrade)

This is what makes the system actually smart instead of just pattern-matching.
The orchestrator gains an optional `context` parameter carrying real execution
metrics. The rule engine and confidence calculator use these to make better decisions.

### Changes to `src/agent/orchestrator.py`

**`process()` signature** — add optional `context`:

```python
def process(self, user_query: str, sql: str | None = None,
            context: dict | None = None) -> AnalysisResponse:
```

**`_fixed_pipeline()` — pass context to rule engine and confidence**:

```python
def _fixed_pipeline(self, user_query, sql, chain, context=None):
    # ... existing steps 1-3 unchanged ...

    # Step 4: rule engine — NOW receives real metrics context
    rule_findings = self.rule_engine.analyze(sql, context=context) if sql else []

    # ... existing steps 5-6 ...

    # Confidence — NOW uses real evidence
    confidence = self._calculate_confidence(
        rule_findings, rag_results, llm_used=False, context=context
    )
```

### Changes to `src/analyzer/rule_engine.py`

**`analyze()` — accept context and suppress false positives on fast queries**:

```python
def analyze(self, sql: str, context: dict | None = None) -> list[Finding]:
    """Run all rules. If real metrics are provided via context, use them
    to suppress false positives on queries that are actually fast."""
    if not sql or not sql.strip():
        return []

    findings: list[Finding] = []
    ctx = context or {}
    real_time_ms = ctx.get("execution_time_ms")
    real_rows = ctx.get("rows_examined")
    explain_type = ctx.get("explain_type")
    explain_key = ctx.get("explain_key")

    # ... existing rule detection logic (AP001-AP007) stays the same ...

    # NEW: If we have real metrics, adjust severity based on actual evidence
    if real_time_ms is not None:
        adjusted = []
        for f in findings:
            # Fast query (<100ms) → downgrade all severities
            if real_time_ms < 100:
                f = Finding(
                    rule=f.rule,
                    severity="info",
                    message=f.message + f" (but query ran in {real_time_ms:.0f}ms — acceptable)",
                    fix=f.fix,
                )
            # Medium-speed query (100-500ms) → downgrade critical to warning
            elif real_time_ms < 500 and f.severity == "critical":
                f = Finding(
                    rule=f.rule,
                    severity="warning",
                    message=f.message + f" (query ran in {real_time_ms:.0f}ms)",
                    fix=f.fix,
                )
            # Slow query (>500ms) → UPGRADE severity, add real evidence
            elif real_time_ms >= 500:
                evidence = f" [REAL: {real_time_ms:.0f}ms"
                if real_rows:
                    evidence += f", {real_rows:,} rows examined"
                if explain_type:
                    evidence += f", EXPLAIN type={explain_type}"
                if explain_key is None:
                    evidence += ", no index used"
                evidence += "]"
                f = Finding(
                    rule=f.rule,
                    severity="critical" if real_time_ms > 1000 else f.severity,
                    message=f.message + evidence,
                    fix=f.fix,
                )
            adjusted.append(f)
        findings = adjusted

    return findings
```

**The result** — smart decisions backed by evidence:

```
# config_table (500 rows): SELECT * → 2ms
#   Rule: NO_WHERE_CLAUSE
#   Before: severity=critical, message="full table scan"
#   After:  severity=info, message="full table scan (but query ran in 2ms — acceptable)"
#   → No alert generated (severity too low)

# salaries (2.8M rows): SELECT * → 3847ms
#   Rule: NO_WHERE_CLAUSE
#   Before: severity=critical, message="full table scan"
#   After:  severity=critical, message="full table scan [REAL: 3847ms, 2,844,047 rows, EXPLAIN type=ALL, no index]"
#   → Alert generated with real evidence
```

### Changes to `_calculate_confidence()` — boost with real evidence

```python
def _calculate_confidence(self, rule_findings, rag_results,
                          llm_used=False, context=None):
    score = 0.0
    # ... existing rule and RAG scoring ...

    # NEW: Real execution evidence → strong confidence boost
    ctx = context or {}
    if ctx.get("execution_time_ms") is not None:
        real_ms = ctx["execution_time_ms"]
        if real_ms > 1000:
            score += 0.25    # very slow → high confidence in diagnosis
        elif real_ms > 500:
            score += 0.15    # slow → moderate confidence boost
        # EXPLAIN type=ALL → confirms full scan diagnosis
        if ctx.get("explain_type") == "ALL" and ctx.get("explain_key") is None:
            score += 0.10

    return round(min(score, 1.0), 3)
```

---

## M4 — PAS Simulator (`src/pas/`)

The simulated Insurance PAS application. Runs business operations, each executing
real SQL against MySQL via MonitoredConnection.

### File structure

```
src/pas/
├── __init__.py
├── operations.py      # PAS_OPERATIONS list — 6 insurance workflows
└── simulator.py       # PASSimulator class — runs operations, emits events
```

### `src/pas/operations.py`

```python
PAS_OPERATIONS = [
    {
        "id": 1,
        "name": "Monthly Premium Report",
        "narrative": "Finance team requesting monthly premium payment summary across all departments.",
        "sql": "SELECT * FROM salaries",
        "expected_slow": True,
    },
    {
        "id": 2,
        "name": "Policyholder Directory Lookup",
        "narrative": "Customer service searching policyholder by first name (unindexed field).",
        "sql": "SELECT * FROM employees WHERE first_name = 'Georgi'",
        "expected_slow": True,
    },
    {
        "id": 3,
        "name": "Compliance Policy Audit",
        "narrative": "Compliance team auditing policies by enrollment year stored in JSON metadata.",
        "sql": "SELECT * FROM employees WHERE JSON_EXTRACT(metadata, '$.hire_year') = '1986'",
        "expected_slow": True,
    },
    {
        "id": 4,
        "name": "Active High-Value Policies Report",
        "narrative": "Management requesting high-premium active policy report with department and coverage details.",
        "sql": ("SELECT e.emp_no, e.first_name, e.last_name, s.salary, t.title, d.dept_name "
                "FROM employees e "
                "JOIN salaries s ON e.emp_no = s.emp_no "
                "JOIN titles t ON e.emp_no = t.emp_no "
                "JOIN dept_emp de ON e.emp_no = de.emp_no "
                "JOIN departments d ON de.dept_no = d.dept_no "
                "WHERE s.salary > 80000"),
        "expected_slow": True,
    },
    {
        "id": 5,
        "name": "Claims Subquery Analysis",
        "narrative": "Actuarial team pulling payment history for long-tenure policyholders via nested subquery.",
        "sql": ("SELECT * FROM salaries "
                "WHERE emp_no IN ("
                "  SELECT emp_no FROM employees WHERE hire_date < '1990-01-01'"
                ")"),
        "expected_slow": True,
    },
    {
        "id": 6,
        "name": "Single Policy Fast Lookup",
        "narrative": "Claims adjustor doing point lookup for policy #10001 — primary key indexed.",
        "sql": "SELECT emp_no, first_name, last_name FROM employees WHERE emp_no = 10001",
        "expected_slow": False,
    },
]
```

### `src/pas/simulator.py`

```python
class PASSimulator:
    """Simulated PAS that runs insurance operations against a real database."""

    def __init__(self, conn, on_operation_start=None, on_query_result=None,
                 on_operation_complete=None):
        self._conn = conn                          # MonitoredConnection
        self._on_start = on_operation_start        # callback(op_index, op)
        self._on_result = on_query_result          # callback(op_index, op, event, row_count)
        self._on_complete = on_operation_complete   # callback(summary_dict)
        self._paused = False
        self._running = False

    def run_once(self):
        """Run all operations once and return summary."""
        results = []
        for i, op in enumerate(PAS_OPERATIONS):
            if self._on_start:
                self._on_start(i, op)

            try:
                cursor = self._conn.cursor()
                cursor.execute(op["sql"])
                rows = cursor.fetchall()
                row_count = len(rows)
                event = self._conn.monitor.history[-1]
            except Exception as exc:
                event = None
                row_count = 0

            results.append({"op": op, "event": event, "row_count": row_count})

            if self._on_result:
                self._on_result(i, op, event, row_count)

        summary = self._conn.monitor.get_summary()
        if self._on_complete:
            self._on_complete(summary)
        return summary

    def run_continuous(self, delay_between_ops=3.0):
        """Run operations in a loop (for TUI mode). Stops on stop()."""
        self._running = True
        while self._running:
            self.run_once()
            for _ in range(int(delay_between_ops * 10)):
                if not self._running:
                    break
                while self._paused:
                    time.sleep(0.5)
                time.sleep(0.1)

    def pause(self): self._paused = True
    def resume(self): self._paused = False
    def stop(self): self._running = False
```

---

## M5 — Demo Entry Point (`demo_live.py`)

### Default mode: Rich Console output (no TUI)

This is the **primary demo mode**. Runs automatically, shows every step
sequentially in the terminal using Rich. Zero risk of layout bugs.

```bash
# Start MySQL (first time ~3 min for data import, then ~5 sec)
docker compose up -d

# Run the automated demo
python demo_live.py
```

The script:
1. Checks MySQL is reachable (retries with clear error message if not)
2. Shows SDK integration explanation (2-line change pitch)
3. Creates MonitoredConnection with orchestrator
4. Creates PASSimulator with Rich rendering callbacks
5. Runs all 6 operations sequentially
6. For each operation:
   - Prints business context + SQL
   - Executes query (real timing)
   - Prints real metrics (execution time, EXPLAIN type/key, rows)
   - If SLOW: prints each AI pipeline step as it happens
   - If FAST: prints "✅ No alert — query is healthy"
7. Prints monitoring summary

### Sample output (default mode)

```
╔══════════════════════════════════════════════════════════════════════╗
║  🏢 Insurance PAS — Automated SQL Performance Monitor               ║
║                                                                      ║
║  A simulated PAS runs real SQL against a live MySQL database.        ║
║  The AI monitoring SDK watches silently and auto-detects slow        ║
║  queries — showing every intermediate analysis step.                 ║
║                                                                      ║
║  SDK integration: 2-line change to add monitoring to ANY system:     ║
║                                                                      ║
║    - from: conn = mysql.connector.connect(...)                       ║
║    + to:   conn = MonitoredConnection(...)                           ║
╚══════════════════════════════════════════════════════════════════════╝


━━━━━━━━ Operation 1/6: Monthly Premium Report ━━━━━━━━

📋 Finance team requesting monthly premium payment summary
   across all departments.

🔍 SQL: SELECT * FROM salaries

─── Real Execution Metrics (captured by SDK) ──────────────

   ⏱  Execution Time : 3,847ms            ← real, timed by SDK
   📊 Rows Examined   : 2,844,047          ← real, from EXPLAIN
   📊 Rows Returned   : 2,844,047          ← real, from cursor
   🔍 EXPLAIN type    : ALL                ← real, full table scan
   🔑 EXPLAIN key     : NONE               ← real, no index used

   Verdict: ⚠️  SLOW (3,847ms > 500ms threshold) → auto-analyzing...

─── AI Pipeline (auto-triggered) ──────────────────────────

   Step 1 │ Intent Classification
          │ → query_analysis
          │
   Step 2 │ SQL Extraction
          │ → SELECT * FROM salaries
          │
   Step 3 │ Rule Engine (context-aware)
          │ → 🔴 NO_WHERE_CLAUSE [critical]
          │      full table scan reading every row
          │      [REAL: 3,847ms, 2,844,047 rows, EXPLAIN type=ALL, no index]
          │ → ⚠️  SELECT_STAR [warning]
          │      fetches all columns including large fields
          │ → ⚠️  NO_LIMIT [warning]
          │      unbounded result set
          │
   Step 4 │ RAG Retrieval
          │ → 3 similar cases found:
          │     1. full_table_scan_policy (rerank: 0.94)
          │     2. select_star_claims (rerank: 0.87)
          │     3. missing_index_scan (rerank: 0.82)
          │
   Step 5 │ Query Rewriter
          │ → 3 transformations applied:
          │     ✏️  SELECT * → SELECT emp_no, salary, from_date, to_date
          │     ✏️  Added WHERE to_date > CURRENT_DATE
          │     ✏️  Added LIMIT 100 OFFSET 0
          │ → Index: CREATE INDEX idx_to_date ON salaries(to_date);
          │
   Step 6 │ Confidence: 0.93
          │   Rule evidence: 0.40 (3 findings)
          │   RAG match:     0.38 (rerank 0.94)
          │   Real metrics:  0.15 (3847ms, confirmed slow)

┌─── 🚨 ALERT ────────────────────────────────────────────────────┐
│ CRITICAL · 93% confidence · query_analysis                       │
│                                                                  │
│ Evidence: 3,847ms | 2,844,047 rows | EXPLAIN ALL | key: NONE    │
│                                                                  │
│ Problem: Full table scan reading every row — no WHERE clause     │
│ Root Cause: No filtering on 2.8M row table + SELECT * fetches    │
│ all columns. EXPLAIN confirms type=ALL with no index.            │
│                                                                  │
│ Suggestions:                                                     │
│  1. Add WHERE clause with indexed column                         │
│  2. Replace SELECT * with specific columns                       │
│  3. Add LIMIT for bounded result set                             │
│                                                                  │
│ Rewritten SQL:                                                   │
│  SELECT emp_no, salary, from_date, to_date                       │
│  FROM salaries                                                   │
│  WHERE to_date > CURRENT_DATE                                    │
│  LIMIT 100 OFFSET 0;                                             │
│                                                                  │
│ Index: CREATE INDEX idx_to_date ON salaries(to_date);            │
│ Estimated improvement: ~95-99% faster                            │
└──────────────────────────────────────────────────────────────────┘


━━━━━━━━ Operation 6/6: Single Policy Fast Lookup ━━━━━━━━

📋 Claims adjustor doing point lookup for policy #10001 —
   primary key indexed.

🔍 SQL: SELECT emp_no, first_name, last_name FROM employees WHERE emp_no = 10001

─── Real Execution Metrics (captured by SDK) ──────────────

   ⏱  Execution Time : 0.4ms
   📊 Rows Examined   : 1
   🔍 EXPLAIN type    : const             ← primary key lookup
   🔑 EXPLAIN key     : PRIMARY           ← using primary key

   Verdict: ✅ FAST (0.4ms < 500ms threshold)

   ⏭  No alert — query is healthy. SDK logged it and moved on.


╔══════════════════════════════════════════════════════════════════╗
║  📊 MONITORING SUMMARY                                          ║
╠══════════════════════════════════════════════════════════════════╣
║  Total queries executed  : 6                                     ║
║  Actually slow (>500ms)  : 4 (67%)     ← alerts generated       ║
║  Actually fast (<500ms)  : 2 (33%)     ← correctly ignored      ║
║  Slowest: SELECT * FROM salaries (3,847ms)                       ║
║  Fastest: SELECT ... WHERE emp_no = 10001 (0.4ms)               ║
║  Avg execution time      : 1,247ms                               ║
║  False positives         : 0           ← no alerts on fast queries║
╚══════════════════════════════════════════════════════════════════╝
```

### Bonus mode: Split-screen TUI

```bash
python demo_live.py --tui
```

If the evaluator wants the live split-screen experience (PAS activity left,
AI analysis right), they can opt in. This is a **bonus**, not the primary demo.

The TUI uses the same PASSimulator and MonitoredConnection, but renders
into a Textual split-screen layout with real-time updates.

If the TUI has any issues, the default Rich console mode always works.

---

## M6 — Split-Screen TUI (Bonus: `cli/live_monitor.py`)

A separate Textual app (does NOT modify the existing `cli/tui.py`).

### Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ 🏦 Insurance PAS Live Monitor       offline · KB:10 · Cache:0       │
├─────────────────────────────┬────────────────────────────────────────┤
│ 🏢 PAS Activity             │ 🤖 AI Monitor                         │
│                             │                                        │
│ [timestamp] OPERATION n/6   │ ⚡ Query intercepted                   │
│ Business narrative...       │ ⏱ EXPLAIN running...                   │
│ ▶ Executing query...        │ 🔍 RAG: searching...                   │
│   SQL shown here            │ ⚙️  Rules: findings shown...            │
│                             │ ✍️  Rewriting...                        │
│ ✅/❌ Result + metrics       │ ✅ ANALYSIS COMPLETE                   │
│                             │ 🔴 Severity + confidence               │
├─────────────────────────────┴────────────────────────────────────────┤
│ 🔴 AUTO-DETECTED: [latest alert summary]                             │
├──────────────────────────────────────────────────────────────────────┤
│ SPACE Pause │ R Restart │ Ctrl+C Quit                                │
└──────────────────────────────────────────────────────────────────────┘
```

### Implementation approach

- `cli/live_monitor.py` — new Textual App with `Horizontal` layout
- `cli/live_monitor.tcss` — CSS for the split layout
- PAS simulator runs in `@work(thread=True)`
- Step callbacks use `call_from_thread()` to update both panels
- Reuses `_build_response_panel()` logic from existing `cli/tui.py`
- Alert bar at bottom updates on each new alert
- SPACE to pause/resume, Ctrl+C to quit

---

## M7 — MCP Tool Extension

### New tool in `src/mcp/server.py`

```python
@mcp.tool()
def monitor_query(sql: str, host: str = "localhost", port: int = 3307,
                  user: str = "monitor", password: str = "monitor_pw",
                  database: str = "employees") -> dict:
    """Execute a SQL query on a real MySQL database and auto-analyze if slow.

    Returns real execution time, EXPLAIN output, and AI analysis.
    This tool connects to a live database — the SQL is actually executed.
    """
```

---

## M8 — Config + Dependencies

### `requirements.txt` — add:
```
mysql-connector-python>=9.0.0
```

### `src/config.py` — add to Settings:
```python
# ── MySQL Monitor ─────────────────────────────────────
mysql_host: str = "localhost"
mysql_port: int = 3307
mysql_user: str = "monitor"
mysql_password: str = "monitor_pw"
mysql_database: str = "employees"
monitor_slow_threshold_ms: float = 500.0
monitor_auto_explain: bool = True
```

### `.env.example` — add:
```bash
# ── MySQL Monitor (Phase 3 — live query monitoring) ────
MYSQL_HOST=localhost
MYSQL_PORT=3307
MYSQL_USER=monitor
MYSQL_PASSWORD=monitor_pw
MYSQL_DATABASE=employees
MONITOR_SLOW_THRESHOLD_MS=500.0
MONITOR_AUTO_EXPLAIN=true
```

---

## M9 — Tests

### `tests/test_monitor.py` (unit tests, mocked — no MySQL needed)

- MonitorConfig / ExplainRow / QueryMetrics / MonitorEvent model validation
- `MonitorConfig.from_settings()` builds correctly
- MonitoredCursor timing capture (mock the real cursor with `time.sleep`)
- Slow threshold detection: mock 600ms → `is_slow=True`
- Fast threshold detection: mock 10ms → `is_slow=False`
- Step callback fires in correct order
- Monitor history tracking
- Monitor summary statistics

### `tests/test_pas.py` (unit tests, mocked)

- PAS_OPERATIONS has expected structure (id, name, narrative, sql, expected_slow)
- PASSimulator calls `on_operation_start` before `on_query_result`
- PASSimulator `run_once()` returns summary dict
- PASSimulator `pause()` / `resume()` / `stop()` work

### `tests/test_monitor_integration.py` (auto-skip if no MySQL)

```python
@pytest.mark.skipif(not mysql_available(), reason="MySQL not available on port 3307")
```

- Real connection to MySQL works
- `SELECT * FROM salaries` flagged as slow (>500ms)
- `SELECT ... WHERE emp_no = 10001` NOT flagged (fast, PK lookup)
- EXPLAIN output is populated with real data
- Auto-analysis triggered and `event.analysis` populated
- Context-aware rule engine: fast query findings have `severity="info"`

### `tests/test_context_rules.py` (unit tests — no MySQL needed)

- Rule engine with `context={"execution_time_ms": 2}` → severity downgraded to "info"
- Rule engine with `context={"execution_time_ms": 3847}` → severity stays "critical"
- Rule engine with no context (backward compatible) → existing behavior unchanged
- Confidence calculation with real metrics context → higher score
- Confidence calculation without context → same as before

---

## M10 — Graceful Degradation

### If MySQL is not running

```
$ python demo_live.py

╔══════════════════════════════════════════════════════════╗
║  ❌ MySQL is not available on localhost:3307             ║
║                                                          ║
║  To start the demo database:                             ║
║    docker compose up -d                                  ║
║                                                          ║
║  First run takes ~3 minutes (importing 4.1M rows).       ║
║  Subsequent starts take ~5 seconds.                      ║
║                                                          ║
║  To check status:                                        ║
║    docker compose ps                                     ║
╚══════════════════════════════════════════════════════════╝
```

### Existing features still work without MySQL

The manual query CLI (`python -m cli.main`), REST API, MCP server, and all
existing tests work exactly as before — they don't require MySQL. Phase 3
adds the live monitoring capability on top without breaking anything.

---

## Implementation Order

```
Step 1: Docker MySQL + init scripts (M1)
        → docker compose up works, data imported, JSON column added

Step 2: Config + dependencies (M8)
        → MySQL settings in config.py, mysql-connector in requirements.txt

Step 3: Monitor SDK (M2)
        → MonitoredConnection, MonitoredCursor, QueryMonitor, models
        → tests/test_monitor.py passes (mocked)

Step 4: Context-aware AI pipeline (M3)
        → orchestrator.process() accepts context
        → rule engine uses real metrics to adjust severity
        → confidence uses real evidence
        → tests/test_context_rules.py passes
        → ALL existing tests still pass (backward compatible)

Step 5: PAS Simulator (M4)
        → operations.py, simulator.py
        → tests/test_pas.py passes (mocked)

Step 6: Demo script — Rich Console mode (M5)
        → demo_live.py — default mode, sequential Rich output
        → Graceful MySQL check (M10)
        → Integration tests pass with Docker (M9)

Step 7: Split-screen TUI — bonus (M6)
        → cli/live_monitor.py, cli/live_monitor.tcss
        → demo_live.py --tui flag

Step 8: MCP tool + docs (M7)
        → monitor_query in MCP server
        → README.md updated
```

Steps 1-6 are **essential**. Steps 7-8 are **bonus**.

Existing tests must pass at every step — Phase 3 is purely additive.

---

## Files Summary

| File | Action | Essential? | Purpose |
|------|--------|------------|---------|
| `docker-compose.yml` | **Create** | ✅ | MySQL 8.0 container |
| `docker/initdb/01_download_employees.sh` | **Create** | ✅ | Import employees DB |
| `docker/initdb/02_post_setup.sql` | **Create** | ✅ | JSON column, drop indexes, perms |
| `src/monitor/__init__.py` | **Create** | ✅ | Package exports |
| `src/monitor/models.py` | **Create** | ✅ | MonitorConfig, ExplainRow, QueryMetrics, MonitorEvent |
| `src/monitor/connection.py` | **Create** | ✅ | MonitoredConnection + MonitoredCursor |
| `src/monitor/monitor.py` | **Create** | ✅ | QueryMonitor with step callbacks |
| `src/pas/__init__.py` | **Create** | ✅ | Package exports |
| `src/pas/operations.py` | **Create** | ✅ | 6 PAS insurance operations |
| `src/pas/simulator.py` | **Create** | ✅ | PASSimulator — runs operations, emits events |
| `demo_live.py` | **Create** | ✅ | Main demo: Rich console (default) + TUI (--tui) |
| `tests/test_monitor.py` | **Create** | ✅ | Monitor SDK unit tests (mocked) |
| `tests/test_pas.py` | **Create** | ✅ | PAS Simulator unit tests (mocked) |
| `tests/test_context_rules.py` | **Create** | ✅ | Context-aware rule engine tests |
| `tests/test_monitor_integration.py` | **Create** | ✅ | Integration tests (Docker MySQL) |
| `src/agent/orchestrator.py` | **Modify** | ✅ | Add `context` param to `process()` + `_fixed_pipeline()` |
| `src/analyzer/rule_engine.py` | **Modify** | ✅ | Accept `context`, adjust severity with real metrics |
| `src/config.py` | **Modify** | ✅ | Add MySQL/monitor settings |
| `requirements.txt` | **Modify** | ✅ | Add mysql-connector-python |
| `.env.example` | **Modify** | ✅ | Add MySQL env vars |
| `cli/live_monitor.py` | **Create** | Bonus | Split-screen TUI |
| `cli/live_monitor.tcss` | **Create** | Bonus | TUI layout CSS |
| `src/mcp/server.py` | **Modify** | Bonus | Add monitor_query tool |
| `README.md` | **Modify** | ✅ | Add live monitoring docs |
| `CLAUDE.md` | **Modify** | ✅ | Add monitor/pas to architecture |

**Essential**: 20 files (15 new, 5 modified)
**Bonus**: 3 files (2 new, 1 modified)

---

## What This Achieves

| Before (Phase 1+2) | After (Phase 3) |
|---------------------|-----------------|
| User types "why is this slow?" | PAS runs → AI auto-detects slow queries |
| Text pattern matching only | Real MySQL: real timing, real EXPLAIN, real rows |
| `SELECT * FROM config_table` → CRITICAL (wrong) | → ✅ 2ms, info severity (correct) |
| `SELECT * FROM salaries` → CRITICAL (lucky) | → 🔴 3,847ms, real evidence (correct) |
| `WHERE policy_id = 123` → WARNING (wrong) | → ✅ 0.4ms, PK lookup (correct) |
| Confidence is a guess | Confidence boosted by real execution evidence |
| No way to add to existing apps | 2-line change: `MonitoredConnection` drop-in SDK |
| Demo requires typing SQL | `python demo_live.py` — runs itself |
| Intermediate steps hidden | Every pipeline step visible in output |
| "Fancy UI" risk | Default: Rich console output. TUI: opt-in bonus only |
