# Phase 2 — Enhancement & Polish Plan

> **Goal**: Transform the system from "working backend with basic CLI" into an
> impressive full-screen TUI application — like Claude Code — that shows its
> intelligence transparently and lets the user interact naturally.
>
> **Estimated effort**: ~6 hours across remaining time.
> **Files touched**: 3 modified, 3 new.

---

## Overview — What Changes

| # | Enhancement | File(s) | Effort | Impact |
|---|-------------|---------|--------|--------|
| **E1** | Orchestrator — expose RAG case metadata + wire A/B suggestions | `src/agent/orchestrator.py` | 30 min | Enables TUI to show case titles, scores. Fixes A/B being decorative. |
| **E2** | Enrich `metrics_history.json` — realistic anomaly-detectable data | `data/metrics_history.json` | 15 min | Anomaly demo shows genuine statistical detection. |
| **E3** | **Full-screen Textual TUI app** — Claude Code-style interface | `cli/tui.py` (new) + CSS | 3 hrs | Biggest differentiator. Professional interactive terminal app. |
| **E4** | README.md — all mandatory sections | `README.md` (new) | 1 hr | Required deliverable. 10% of grade. |
| **E5** | Bug fixes in old CLI + keep as fallback | `cli/main.py` | 15 min | Backwards compatibility for single-query mode. |
| **E6** | Add `textual` to dependencies | `requirements.txt` | 1 min | One package. |

---

## E1 — Orchestrator: RAG Metadata + A/B Wiring

### E1.1 — Expose full RAG case objects in response metadata

**Why**: Currently `response.similar_cases` stores only case IDs (`["case_001", "case_006"]`).
The TUI, API, and MCP clients all want to show titles, categories, and relevance scores —
but that data is lost after retrieval. By storing the top-3 case summaries in `metadata["rag_cases"]`,
every interface gets rich case info without loading the knowledge base separately.

**Where**: `src/agent/orchestrator.py`

**In `_template_response()`** — add to metadata before returning:

```python
metadata["rag_cases"] = [
    {
        "case_id": c.get("case_id"),
        "title": c.get("title"),
        "category": c.get("category"),
        "severity": c.get("severity"),
        "_rerank_score": c.get("_rerank_score"),
        "_distance": c.get("_distance"),
    }
    for c in rag_cases[:3]
]
```

**In `_parse_llm_response()`** — same addition using `tool_results.get("search_cases", [])`.

### E1.2 — Wire A/B engine into actual suggestion flow

**Why**: The `ABTestingEngine.generate_suggestions()` exists with two real strategies
(Conservative: safe fixes, Aggressive: materialized views, partitioning, Redis cache).
But it's never called. Both A/B variants get identical suggestions. This fixes that.

**Where**: `src/agent/orchestrator.py` → `_template_response()`

```python
from src.ab_testing.ab_engine import ABTestingEngine
ab = ABTestingEngine()
variant = ab.get_variant(user_query or "")

context = {
    "table": tables[0] if tables else "unknown",
    "is_select_star": any(f.rule == "SELECT_STAR" for f in rule_findings),
    "no_where": any(f.rule == "NO_WHERE_CLAUSE" for f in rule_findings),
    "no_limit": any(f.rule == "NO_LIMIT" for f in rule_findings),
    "uses_json_extract": any(f.rule == "JSON_EXTRACT_IN_WHERE" for f in rule_findings),
    "missing_index": bool(rule_findings),
    "join_count": top_case.get("context", {}).get("join_count", 0),
    "frequency": top_case.get("frequency", ""),
    "table_size_rows": top_case.get("context", {}).get("table_size_rows", 0),
    "schema_columns": [],
}

ab_extras = ab.generate_suggestions(context, variant)
for s in ab_extras:
    if s not in suggestions:
        suggestions.append(s)

metadata["ab_variant"] = variant
```

---

## E2 — Enrich Metrics History

**Why**: case_010 already has 16 data points with a detectable spike (980ms → 50,000ms).
Add one more scenario for variety: gradual degradation + sudden improvement after fix.

**Where**: `data/metrics_history.json` — add a new entry for `case_002`:

```json
{
  "query_id": "case_002",
  "query": "SELECT * FROM policy_data WHERE JSON_EXTRACT(data, '$.policy.state') = 'CA'",
  "description": "JSON filter query — gradual degradation then recovery after index",
  "metrics": [
    {"timestamp": "2025-01-01T00:00:00Z", "latency_ms": 25000, "rows_scanned": 50000000},
    {"timestamp": "2025-01-01T01:00:00Z", "latency_ms": 25500, "rows_scanned": 50000000},
    {"timestamp": "2025-01-01T02:00:00Z", "latency_ms": 26200, "rows_scanned": 50000000},
    {"timestamp": "2025-01-01T03:00:00Z", "latency_ms": 26800, "rows_scanned": 50000000},
    {"timestamp": "2025-01-01T04:00:00Z", "latency_ms": 27100, "rows_scanned": 50000000},
    {"timestamp": "2025-01-01T05:00:00Z", "latency_ms": 27600, "rows_scanned": 50000000},
    {"timestamp": "2025-01-01T06:00:00Z", "latency_ms": 28500, "rows_scanned": 50000000},
    {"timestamp": "2025-01-01T07:00:00Z", "latency_ms": 29200, "rows_scanned": 50000000},
    {"timestamp": "2025-01-01T08:00:00Z", "latency_ms": 30100, "rows_scanned": 50000000},
    {"timestamp": "2025-01-01T09:00:00Z", "latency_ms": 31000, "rows_scanned": 50000000},
    {"timestamp": "2025-01-01T10:00:00Z", "latency_ms": 32000, "rows_scanned": 50000000},
    {"timestamp": "2025-01-01T11:00:00Z", "latency_ms": 120,   "rows_scanned": 45000},
    {"timestamp": "2025-01-01T12:00:00Z", "latency_ms": 115,   "rows_scanned": 45000},
    {"timestamp": "2025-01-01T13:00:00Z", "latency_ms": 118,   "rows_scanned": 45000}
  ]
}
```

Two anomaly patterns for the demo:
- **case_010**: Normal → sudden spike → recovery (lock contention)
- **case_002**: Gradual degradation → dramatic improvement after index added

---

## E3 — Full-Screen Textual TUI Application

### Why Textual (not just Rich print statements)

| | Current Rich CLI | Textual TUI |
|---|---|---|
| **Experience** | Text scrolls past, gone forever | Full-screen app, scrollable history |
| **Input** | `input()` blocks everything | Dedicated input widget, non-blocking |
| **Status** | None visible | Live header bar with mode, cache, KB count |
| **Commands** | Type text, hope it works | Footer keybindings: F1 Help, F2 Cases, etc. |
| **Analysis** | UI freezes during processing | Background worker thread, spinner visible |
| **Feel** | Script output | Professional application (like Claude Code) |

**Dependency**: `pip install textual` — one package, built by the Rich team,
uses Rich renderables directly inside widgets. Zero conflict.

### E3.1 — App Layout (CSS-styled full-screen)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ 🧠 Query Intelligence Engine        offline · KB: 10 · Vectors: 10 · Cache: 0 │ ← Header (live stats)
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Welcome to Query Intelligence Engine                                        │
│  Insurance PAS Performance Analyzer                                          │
│                                                                              │
│  Ask anything about SQL performance, or paste SQL directly.                  │
│  ─────────────────────────────────────────────────────────                    │
│                                                                              │
│  ┌─ YOU ──────────────────────────────────────────────────────┐               │
│  │ Why is SELECT * FROM policy_data slow?                     │               │
│  └────────────────────────────────────────────────────────────┘               │
│                                                                              │
│  ┌─ ANALYSIS ─────────────────────────────────────────────────┐               │
│  │ 🔴 FULL_TABLE_SCAN · CRITICAL · 95% confidence             │               │
│  │                                                            │               │  ← VerticalScroll
│  │ PROBLEM                                                    │               │    (main area)
│  │ Full table scan reads all 50M rows without filtering.      │               │
│  │                                                            │               │
│  │ RULE VIOLATIONS                                            │               │
│  │ ┌──────────────────┬──────────┬──────────────────────────┐ │               │
│  │ │ Rule             │ Severity │ Fix                       │ │               │
│  │ ├──────────────────┼──────────┼──────────────────────────┤ │               │
│  │ │ SELECT_STAR      │ warning  │ Replace with column list  │ │               │
│  │ │ NO_WHERE_CLAUSE  │ critical │ Add WHERE clause          │ │               │
│  │ └──────────────────┴──────────┴──────────────────────────┘ │               │
│  │                                                            │               │
│  │ REWRITTEN SQL                                              │               │
│  │ SELECT policy_id, premium_amount, state, status            │               │
│  │ FROM   policy_data                                         │               │
│  │ WHERE  status = 'ACTIVE'                                   │               │
│  │ LIMIT  100 OFFSET 0;                                       │               │
│  │                                                            │               │
│  │ SIMILAR CASES                                              │               │
│  │ 1. Full Table Scan on policy_data (0.94) · case_001        │               │
│  │ 2. Aggregation Query Full Scan (0.71) · case_006           │               │
│  │                                                            │               │
│  │ REASONING TRACE                                            │               │
│  │ 1. RAG search → 10 candidates → reranked to 3             │               │
│  │ 2. Rule engine → 3 findings                               │               │
│  │ 3. Confidence → 0.95 · Mode: offline · Time: 847ms        │               │
│  └────────────────────────────────────────────────────────────┘               │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ > Type your query here...                                                    │ ← Input widget
├──────────────────────────────────────────────────────────────────────────────┤
│ F1 Help │ F2 Cases │ F3 Anomaly │ F4 Status │ F5 Stats │ Ctrl+C Quit       │ ← Footer (keybindings)
└──────────────────────────────────────────────────────────────────────────────┘
```

### E3.2 — File Structure

```
cli/
├── main.py          # Keep existing — fallback for single-query mode
├── tui.py           # NEW — Textual full-screen app (main entry point)
└── tui.tcss         # NEW — Textual CSS for layout styling
```

**Entry points**:
- `python cli/tui.py` → full-screen TUI (primary demo experience)
- `python cli/main.py "query"` → single-shot mode (backwards compatible)
- `python cli/main.py` → old interactive REPL (still works)

### E3.3 — Textual App Architecture

```python
# cli/tui.py — Full-screen TUI application

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Header, Footer, Input, RichLog, Static
from textual.binding import Binding
from textual.work import work
from rich.panel import Panel
from rich.table import Table


class QueryIntelligenceApp(App):
    """Full-screen TUI for the Query Intelligence Engine."""

    CSS_PATH = "tui.tcss"
    TITLE = "Query Intelligence Engine"

    BINDINGS = [
        Binding("f1", "show_help", "Help"),
        Binding("f2", "show_cases", "Cases"),
        Binding("f3", "run_anomaly", "Anomaly"),
        Binding("f4", "show_status", "Status"),
        Binding("f5", "show_stats", "Stats"),
        Binding("ctrl+c", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="output"):
            yield Static(self._welcome_text(), id="welcome")
        yield Input(placeholder="Ask about SQL performance, or paste SQL...", id="query-input")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize orchestrator and update header with live stats."""
        self._init_orchestrator()
        self._update_subtitle()

    @on(Input.Submitted)
    async def handle_query(self, event: Input.Submitted) -> None:
        """User pressed Enter — process the query."""
        query = event.value.strip()
        if not query:
            return
        event.input.clear()

        output = self.query_one("#output")

        # Show user's query
        await output.mount(Static(
            Panel(query, title="YOU", border_style="blue"),
        ))

        # Show loading indicator
        loading = Static("[bold green]Analyzing...[/bold green]", id="loading")
        await output.mount(loading)
        loading.scroll_visible()

        # Run analysis in background thread (UI stays responsive)
        self._run_analysis(query, loading)

    @work(thread=True)
    def _run_analysis(self, query: str, loading_widget: Static) -> None:
        """Execute orchestrator in a worker thread — UI doesn't freeze."""
        try:
            response = self.orchestrator.process(query)
            # Build Rich renderables from the response
            renderable = self._build_response_panel(response)
            # Update UI from the worker thread
            self.call_from_thread(self._show_result, renderable, loading_widget)
        except Exception as exc:
            self.call_from_thread(
                self._show_result,
                Panel(f"[red]Error: {exc}[/red]", border_style="red"),
                loading_widget,
            )

    def _show_result(self, renderable, loading_widget) -> None:
        """Replace loading indicator with the analysis result."""
        loading_widget.remove()
        output = self.query_one("#output")
        result_widget = Static(renderable)
        output.mount(result_widget)
        result_widget.scroll_visible()
        self._update_subtitle()  # refresh cache count, etc.
```

### E3.4 — Response Panel Builder

The `_build_response_panel()` method converts an `AnalysisResponse` into a Rich
`Group` of renderables (panels, tables, text). This is the same data the old CLI
showed — but now structured inside a bordered panel in the TUI.

```python
def _build_response_panel(self, response) -> Panel:
    """Build a Rich Panel from AnalysisResponse for display in the TUI."""
    from rich.console import Group
    from rich.text import Text

    parts = []

    # ── Severity header ──────────────────────────────────────────
    sev = response.severity.upper()
    conf = int(response.confidence * 100)
    parts.append(Text.from_markup(
        f"[bold]{response.category.upper()}[/bold] · "
        f"Severity: [bold {'red' if sev == 'CRITICAL' else 'yellow'}]{sev}[/] · "
        f"Confidence: {conf}%\n"
    ))

    # ── Problem + Root cause ─────────────────────────────────────
    parts.append(Text.from_markup(f"[bold]PROBLEM[/bold]\n{response.problem}\n"))
    parts.append(Text.from_markup(f"[bold]ROOT CAUSE[/bold]\n{response.root_cause}\n"))

    # ── Rule findings table ──────────────────────────────────────
    if response.rule_findings:
        t = Table(title="Rule Violations", box=box.SIMPLE)
        t.add_column("Rule")
        t.add_column("Severity")
        t.add_column("Fix")
        for f in response.rule_findings:
            t.add_row(f.rule, f.severity, f.fix)
        parts.append(t)

    # ── Suggestions ──────────────────────────────────────────────
    suggestions_text = "\n".join(f"  {i}. {s}" for i, s in enumerate(response.suggestion, 1))
    parts.append(Text.from_markup(f"[bold green]SUGGESTIONS[/bold green]\n{suggestions_text}\n"))

    # ── Rewritten SQL (always shown) ─────────────────────────────
    if response.rewritten_sql and response.rewritten_sql.changes:
        rw = response.rewritten_sql
        parts.append(Panel(rw.rewritten, title="Rewritten SQL", border_style="cyan"))
        if rw.index_suggestions:
            idx_text = "\n".join(rw.index_suggestions)
            parts.append(Text.from_markup(f"[cyan]INDEX SUGGESTIONS[/cyan]\n{idx_text}\n"))
        parts.append(Text.from_markup(
            f"Improvement: [green]{rw.estimated_improvement}[/green]\n"
        ))

    # ── Similar cases (with titles + scores from metadata) ───────
    rag_cases = response.metadata.get("rag_cases", [])
    if rag_cases:
        ct = Table(title="Similar Cases", box=box.SIMPLE)
        ct.add_column("#", width=3)
        ct.add_column("Title")
        ct.add_column("Score", width=8)
        ct.add_column("ID", width=10)
        for i, c in enumerate(rag_cases, 1):
            score = c.get("_rerank_score") or (1.0 - (c.get("_distance") or 0.5))
            ct.add_row(str(i), c.get("title", ""), f"{score:.2f}", c.get("case_id", ""))
        parts.append(ct)

    # ── Reasoning trace (always shown) ───────────────────────────
    if response.explanation_chain:
        rt = Table(title="Reasoning Trace", box=box.SIMPLE)
        rt.add_column("#", width=3)
        rt.add_column("Step")
        rt.add_column("Result")
        for step in response.explanation_chain:
            rt.add_row(
                str(step.get("step", "")),
                step.get("action", step.get("tool", "")),
                str(step.get("result", step.get("matches", step.get("findings", "")))),
            )
        mode = response.metadata.get("mode", "offline")
        time_ms = response.metadata.get("processing_time_ms", "?")
        rt.add_row("", f"Mode: {mode}", f"Time: {time_ms}ms")
        parts.append(rt)

    # Compose all parts into one bordered panel
    border_color = "red" if sev == "CRITICAL" else "yellow" if sev == "HIGH" else "green"
    return Panel(Group(*parts), title="ANALYSIS", border_style=border_color)
```

### E3.5 — Real-Time Data Awareness (Live Header)

The header subtitle is **refreshed after every interaction** — showing live counts
from all data sources. If someone adds cases to `knowledge_base.json` and rebuilds
the vector store, the header immediately reflects the new count.

```python
def _update_subtitle(self) -> None:
    """Update the header subtitle with live stats from all data sources."""
    import json
    from pathlib import Path
    from src.config import settings

    mode = "online" if settings.llm_available else "offline"
    model = settings.llm_model if settings.llm_available else "rules + RAG"
    kb_count = len(json.loads(Path(settings.knowledge_base_path).read_text()))
    vec_count = self.orchestrator.retriever.vector_store.count()
    cache_count = self.orchestrator.cache.size()
    fb_count = len(json.loads(Path(settings.feedback_log_path).read_text()))

    self.sub_title = (
        f"{mode} · {model} · "
        f"KB: {kb_count} · Vectors: {vec_count} · "
        f"Cache: {cache_count} · Feedback: {fb_count}"
    )
```

**What's live** (queried on every refresh, not cached at startup):

| Metric | Source | Changes when... |
|--------|--------|----------------|
| KB cases | `len(knowledge_base.json)` | User adds a case to the JSON file |
| Vector count | `vector_store.count()` | ChromaDB is rebuilt after feedback processing |
| Cache entries | `cache.size()` | Queries are processed (grows) or cache clears (resets) |
| Feedback entries | `len(feedback_log.json)` | User gives feedback (y/n) after each query |
| LLM mode/model | `settings.llm_available` | `.env` changes (requires restart, but shows current) |

### E3.6 — Keybinding Commands

| Key | Command | What it does |
|-----|---------|-------------|
| **F1** | Help | Show all commands, example queries, keyboard shortcuts |
| **F2** | Cases | Show knowledge base as a numbered table. User types a number to analyze that case. |
| **F3** | Anomaly | Run anomaly detector against all time-series in `metrics_history.json`. Show per-method results. |
| **F4** | Status | Show full live data table (all sources, counts, model info) |
| **F5** | Stats | Show feedback statistics + A/B testing win rates |
| **Ctrl+C** | Quit | Exit the app |

#### F2 — Cases Browser

```python
def action_show_cases(self) -> None:
    """Show all 10 knowledge base cases as a Rich table."""
    import json
    from src.config import settings
    cases = json.loads(open(settings.knowledge_base_path).read())

    t = Table(title="Knowledge Base Cases", box=box.ROUNDED)
    t.add_column("#", width=3)
    t.add_column("Title")
    t.add_column("Severity", width=10)
    t.add_column("Category", width=18)
    t.add_column("Exec Time", width=10)
    for i, c in enumerate(cases, 1):
        sev_style = "red" if c["severity"] == "critical" else "yellow" if c["severity"] == "high" else ""
        t.add_row(
            str(i), c["title"],
            f"[{sev_style}]{c['severity']}[/{sev_style}]",
            c["category"],
            f"{c['execution_time_sec']}s",
        )

    output = self.query_one("#output")
    output.mount(Static(Panel(t, title="F2 — Case Browser", border_style="blue")))
    output.mount(Static("[dim]Type a case number (1-10) to analyze it[/dim]"))
```

When the user types a number (1-10) into the input, the app detects it and runs
that case through the orchestrator.

#### F3 — Live Anomaly Detection

```python
def action_run_anomaly(self) -> None:
    """Run anomaly detection on all metrics in metrics_history.json."""
    import json
    from src.config import settings
    from src.anomaly.detector import AnomalyDetector

    metrics_data = json.loads(open(settings.metrics_path).read())
    detector = AnomalyDetector(
        settings.anomaly_zscore_threshold,
        settings.anomaly_iqr_factor,
        settings.anomaly_window_size,
    )

    parts = []
    for entry in metrics_data:
        query_id = entry["query_id"]
        metrics = entry["metrics"]
        result = detector.detect(metrics)

        # Build a table for this time-series
        t = Table(box=box.SIMPLE, title=f"{query_id} — {len(metrics)} samples")
        t.add_column("Method")
        t.add_column("Flagged Indices")
        for method, indices in result.methods_agreed.items():
            marker = " ✓" if indices else ""
            t.add_row(method, str(indices) + marker)

        consensus = result.anomaly_indices
        t.add_row(
            "[bold]Consensus[/bold]",
            f"[bold]{consensus}[/bold]" if consensus else "[green]None — all normal[/green]"
        )
        parts.append(t)

        if result.anomalies_detected:
            values = [m["latency_ms"] for m in metrics]
            normal = [v for i, v in enumerate(values) if i not in set(consensus)]
            normal_avg = sum(normal) / len(normal) if normal else 0
            for idx in consensus:
                spike = values[idx]
                ratio = spike / normal_avg if normal_avg else 0
                parts.append(Text.from_markup(
                    f"  [red]Index [{idx}]: {spike:,.0f}ms ({ratio:.0f}× normal)[/red]"
                ))
            parts.append(Text.from_markup(
                f"  Severity: [bold red]{result.severity.upper()}[/bold red]\n"
            ))
        else:
            parts.append(Text.from_markup("[green]  No anomalies detected ✓[/green]\n"))

    output = self.query_one("#output")
    output.mount(Static(Panel(
        Group(*parts),
        title="F3 — Anomaly Detection (Live)",
        border_style="red",
    )))
```

#### F4 — Full Status Table

```python
def action_show_status(self) -> None:
    """Show comprehensive live system status."""
    stats = self._get_live_stats()
    t = Table(title="System Status — Live Data", box=box.ROUNDED)
    t.add_column("Data Source", style="bold")
    t.add_column("Count", justify="right")
    t.add_column("Location", style="dim")

    t.add_row("Knowledge base cases", str(stats["kb_cases"]), "data/knowledge_base.json")
    t.add_row("Vector store embeddings", str(stats["vector_count"]), "chroma_db/ (ChromaDB)")
    t.add_row("Table schemas", str(stats["schemas"]), "data/schemas.json")
    t.add_row("Anti-pattern rules", str(stats["rules"]), "data/query_patterns.json")
    t.add_row("Metrics time-series", str(stats["metrics_queries"]), "data/metrics_history.json")
    t.add_row("Total metric data points", str(stats["metrics_points"]), "(across all queries)")
    t.add_row("Feedback entries", str(stats["feedback_entries"]), "data/feedback_log.json")
    t.add_row("Cache entries", str(stats["cache_entries"]), "In-memory (resets on restart)")
    t.add_section()
    t.add_row("LLM mode", stats["mode"], stats["model"])
    t.add_row("Embedding model", "local", "all-MiniLM-L6-v2 (22M params)")
    t.add_row("Reranker model", "local", "ms-marco-MiniLM-L-6-v2 (6MB)")

    output = self.query_one("#output")
    output.mount(Static(Panel(t, title="F4 — Status", border_style="green")))
```

### E3.7 — CSS Layout (`cli/tui.tcss`)

```css
/* Full-screen layout — input docked to bottom, output fills remaining space */

#output {
    height: 1fr;
    scrollbar-gutter: stable;
    padding: 1 2;
}

#query-input {
    dock: bottom;
    margin: 0 1;
}

/* Style user query panels */
Static {
    margin: 0 0 1 0;
}

/* Welcome text */
#welcome {
    color: $text-muted;
    padding: 1 2;
}
```

### E3.8 — Smart Input Handling

The Input handler detects special patterns:

```python
@on(Input.Submitted)
async def handle_query(self, event: Input.Submitted) -> None:
    query = event.value.strip()
    if not query:
        return
    event.input.clear()

    # ── Command dispatch ──────────────────────────────
    if query.lower() in ("help", "h", "?"):
        self.action_show_help()
        return
    if query.lower() in ("cases", "case"):
        self.action_show_cases()
        return
    if query.lower() in ("anomaly", "anomalies"):
        self.action_run_anomaly()
        return
    if query.lower() in ("status", "info"):
        self.action_show_status()
        return
    if query.lower() in ("stats", "feedback"):
        self.action_show_stats()
        return

    # ── Case number shortcut (1-10) ───────────────────
    if query.isdigit() and 1 <= int(query) <= len(self.cases):
        case = self.cases[int(query) - 1]
        query = case.get("problem", case.get("title", ""))
        sql = case.get("query")
        # ... run analysis with this case's query + sql
        return

    # ── Normal query — run through orchestrator ────────
    # ... (show user query panel, run worker, show result)
```

---

## E4 — README.md

### Sections (from problem statement requirements):

1. **Problem Understanding** — What we built and why
2. **Architecture Diagram** — ASCII from PLANNING.md
3. **How to Run** — Setup, `.env` config, three entry points:
   - `python cli/tui.py` — full-screen TUI (primary)
   - `python cli/main.py` — single-query CLI
   - `uvicorn api.main:app --reload` — REST API
   - `python -m src.mcp.server` — MCP server
4. **Design Decisions** — Technology choices + rationale
5. **Trade-offs** — What we chose not to build
6. **"If designing for production at scale"** — Mandatory open-ended answer
7. **AI Usage Disclosure** — Tools, what for, what changed
8. **Bonus Features** — SLM, anomaly detection, system-level suggestions

---

## E5 — Bug Fixes in Old CLI

| Bug | Fix |
|-----|-----|
| Missing `import json` | Add at top of `cli/main.py` |
| Double `orch.process()` on argument mode (lines 206-213) | `_run_query()` returns the response; feed it to `_record_feedback()` |
| `chain` command crash | Fixed by `import json` |

The old `cli/main.py` stays as a **fallback** for single-shot queries:
```bash
python cli/main.py "Why is this slow?" --sql "SELECT * FROM policy_data"
```

---

## E6 — Dependencies

Add to `requirements.txt`:

```
textual>=1.0.0
```

That's it. One package. Built by the same team as Rich (Will McGuinness / Textualize).
Uses Rich renderables directly inside Textual widgets. Zero conflicts.

---

## Implementation Order

```
E1 ─── Orchestrator (30 min)          ┐
E2 ─── Metrics data (15 min)          ├── parallel, no dependencies
E6 ─── requirements.txt (1 min)       ┘
       │
       ▼
E3 ─── Textual TUI app (3 hrs)        ── depends on E1 (rag_cases metadata)
       │                                  depends on E2 (anomaly data)
       │
E5 ─── Old CLI bug fixes (15 min)     ── independent
       │
       ▼
E4 ─── README.md (1 hr)               ── last (references final commands/entry points)
```

---

## What This Achieves

| Before (current) | After (Phase 2) |
|---|---|
| `print()` statements scrolling past | Full-screen Textual app with persistent layout |
| No header or status | Live header: mode, KB count, vectors, cache — updates in real time |
| Input blocks the entire process | Background worker thread — UI stays responsive during analysis |
| No keyboard shortcuts | F1-F5 keybindings for Help, Cases, Anomaly, Status, Stats |
| Rewritten SQL hidden behind flag | Always visible in analysis panel |
| Similar cases: just IDs | Full titles + rerank scores + case IDs |
| Reasoning trace hidden | Always shown as a table in the response panel |
| Anomaly detector never demoed | F3 runs live detection on all metrics, shows per-method results |
| No data awareness | F4 Status shows live counts from every data source |
| No README | Full README covering all mandatory sections |
| Evaluator sees "script" | Evaluator sees "application" — like Claude Code |
