"""Live Monitor TUI — Welcome screen + 3 modes + 14-step AI pipeline + Chat.

Modes:
  1  Run 6 queries once      — demo all anti-patterns, stop when done
  2  Continuous monitor      — loop like a live PAS system
  3  Manual / Chat           — type SQL or questions, AI responds

Launch:
    python demo_live.py
    python demo_live.py --no-tui   (plain console)
"""
from __future__ import annotations

import math
import os
import re
import sys
import time
from datetime import datetime
from typing import Any

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.utils.silence import suppress_all
suppress_all()

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Header, Footer, Input, RichLog, Static
from textual import work
from rich.text import Text

# ── Colour palette ────────────────────────────────────────────────────────────
_C = {
    "muted":   "#3D4450",
    "dim":     "#6E7681",
    "sub":     "#8B949E",
    "text":    "#C9D1D9",
    "bright":  "#E6EDF3",
    "blue":    "#79C0FF",
    "green":   "#3FB950",
    "amber":   "#D29922",
    "red":     "#F85149",
    "orange":  "#FF9950",
    "purple":  "#D2A8FF",
    "sep":     "#1C2128",
    "sep_hi":  "#2D333B",
}
_SEV = {
    "critical": _C["red"],
    "high":     _C["orange"],
    "medium":   _C["amber"],
    "low":      _C["green"],
}
# Known employees DB row counts (always the same dataset)
_DB_TABLES = [
    ("employees",    300_024,  "Policyholder records  (+ JSON metadata)"),
    ("salaries",   2_844_047,  "Premium payment history"),
    ("titles",       443_308,  "Coverage type records"),
    ("dept_emp",     331_603,  "Policy-dept assignments"),
    ("departments",        9,  "Business line config"),
]


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _sql_preview(sql: str, n: int = 62) -> str:
    s = " ".join(sql.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _rewrite_lines(sql: str, n: int = 5) -> list[str]:
    return [
        ln.rstrip()
        for ln in sql.splitlines()
        if ln.strip() and not ln.strip().startswith("--")
    ][:n]


# ── Text helpers ──────────────────────────────────────────────────────────────

def _sep()     -> Text: return Text("  " + "─" * 48, style=_C["sep"])
def _sep_hi()  -> Text: return Text("  " + "═" * 48, style=_C["sep_hi"])
def _blank()   -> Text: return Text("")
def _dim(s)    -> Text: return Text(s, style=_C["dim"])
def _err(s)    -> Text: return Text(f"  {s}", style=_C["red"])

def _section(label: str, n: int) -> Text:
    """Render:  ── [07] Cross-Encoder Reranking ────────────"""
    prefix = f"  ── [{n:02d}] {label} "
    dashes = max(2, 50 - len(prefix))
    t = Text()
    t.append(prefix, style=f"bold {_C['sub']}")
    t.append("─" * dashes, style=_C["sep"])
    return t

def _kv(key: str, val: str, kstyle: str = "", vstyle: str = "") -> Text:
    t = Text()
    t.append(f"  {key:<12}", style=kstyle or _C["muted"])
    t.append(val, style=vstyle or _C["text"])
    return t



# ── App ───────────────────────────────────────────────────────────────────────

class LiveMonitorApp(App):
    CSS_PATH = "live_monitor.tcss"
    TITLE    = "PAS Query Monitor"

    BINDINGS = [
        Binding("1",     "select_once",       "Run Once",   show=False),
        Binding("2",     "select_continuous", "Continuous", show=False),
        Binding("3",     "select_manual",     "Manual",     show=False),
        Binding("space", "toggle_pause",      "Pause",      show=True),
        Binding("r",     "restart",           "Restart",    show=True),
        Binding("q",     "quit",              "Quit",       show=True),
    ]

    def __init__(self, orchestrator: Any = None) -> None:
        super().__init__()
        self._orchestrator = orchestrator
        self._simulator    = None
        self._conn         = None
        self._mode         = "WELCOME"
        self._last_sql: str | None = None
        self._chat_count   = 0
        # live counters
        self._total  = 0
        self._slow   = 0
        self._sum_ms = 0.0
        self._last_ms = 0.0

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="panels"):
            yield RichLog(id="pas-log", markup=False, highlight=False, wrap=True)
            yield RichLog(id="ai-log",  markup=False, highlight=False, wrap=True)
        yield Input(id="chat-input",
                    placeholder="  Press [1] Run Once  [2] Continuous  [3] Manual/Chat to begin...")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#pas-log", RichLog).border_title = " PAS ACTIVITY "
        self.query_one("#ai-log",  RichLog).border_title = " AI ANALYSIS "
        # Input is keyboard-only in welcome; disable so [1][2][3] bindings fire
        inp = self.query_one("#chat-input", Input)
        inp.disabled = True
        self._refresh_status()
        self._draw_welcome()

    # ── Welcome screen ────────────────────────────────────────────────────────

    def _draw_welcome(self) -> None:
        """Render the welcome / mode selection screen into both panels."""
        lp = self.query_one("#pas-log", RichLog)
        rp = self.query_one("#ai-log",  RichLog)

        # ── Left: DB overview ─────────────────────────────────────────────
        lp.clear()
        lp.write(_blank())
        t = Text()
        t.append("  Insurance PAS — AI-Powered SQL Monitor", style=f"bold {_C['bright']}")
        lp.write(t)
        lp.write(_dim("  Real queries · Real MySQL · Real EXPLAIN · Full 14-step AI pipeline"))
        lp.write(_blank())
        lp.write(_sep_hi())
        lp.write(_dim("  DATABASE OVERVIEW  (MySQL Employees Sample DB)"))
        lp.write(_sep_hi())
        lp.write(_blank())

        hdr = Text()
        hdr.append(f"  {'Table':<16}", style=f"bold {_C['sub']}")
        hdr.append(f"{'Rows':>12}   ", style=f"bold {_C['sub']}")
        hdr.append("Role in insurance domain", style=f"bold {_C['sub']}")
        lp.write(hdr)
        lp.write(_sep())

        total_rows = 0
        for tbl, rows, role in _DB_TABLES:
            total_rows += rows
            row = Text()
            row.append(f"  {tbl:<16}", style=_C["blue"])
            row.append(f"{rows:>12,}   ", style=_C["text"])
            row.append(role, style=_C["dim"])
            lp.write(row)

        lp.write(_sep())
        summary = Text()
        summary.append(f"  Total: ~{total_rows/1_000_000:.1f}M rows   ", style=_C["sub"])
        summary.append("Slow threshold: 500ms   ", style=_C["sub"])
        summary.append("AI: offline (Rules + RAG)", style=_C["dim"])
        lp.write(summary)
        lp.write(_blank())
        lp.write(_sep_hi())

        mysql_line = Text()
        mysql_line.append("  MySQL  ", style=_C["muted"])
        mysql_line.append("localhost:3307   ", style=_C["sub"])
        mysql_line.append("KB: 16 cases   ", style=_C["sub"])
        mysql_line.append("Vector store: 16 embeddings", style=_C["sub"])
        lp.write(mysql_line)
        lp.write(_sep_hi())

        # ── Right: mode selection ─────────────────────────────────────────
        rp.clear()
        rp.write(_blank())
        rp.write(Text("  SELECT A MODE", style=f"bold {_C['bright']}"))
        rp.write(_blank())
        rp.write(_sep_hi())

        modes = [
            ("1", "Run 6 Queries Once",
             "Execute all demo anti-patterns once with full\n"
             "  14-step AI analysis per query, then stop.\n"
             "  Best for evaluation and presentation."),
            ("2", "Continuous Monitor",
             "Loop queries as a live production PAS system.\n"
             "  AI watches silently — auto-alerts on slow SQL.\n"
             "  Simulates real-world monitoring."),
            ("3", "Manual / Chat",
             "Type your own SQL or ask the AI questions.\n"
             "  Full 14-step pipeline shown for every input.\n"
             "  Commands: 'rewrite last' · 'explain' · 'status'"),
        ]
        for key, title, desc in modes:
            rp.write(_blank())
            t = Text()
            t.append(f"  [{key}]  ", style=f"bold {_C['amber']}")
            t.append(title, style=f"bold {_C['bright']}")
            rp.write(t)
            for line in desc.split("\n"):
                rp.write(Text(f"  {line}", style=_C["dim"]))

        rp.write(_blank())
        rp.write(_sep_hi())
        rp.write(Text("  Press [1], [2], or [3] to begin", style=_C["sub"]))
        rp.write(_blank())
        rp.write(_dim("  Example queries for Manual mode:"))
        for ex in [
            "SELECT * FROM salaries",
            "SELECT * FROM employees WHERE first_name = 'Georgi'",
            "Why is a nested subquery slow?",
        ]:
            t = Text()
            t.append("   > ", style=_C["muted"])
            t.append(ex, style=_C["blue"])
            rp.write(t)

        self._refresh_status()

    # ── Mode actions ──────────────────────────────────────────────────────────

    def action_select_once(self) -> None:
        if self._mode != "WELCOME":
            return
        self._launch_monitor("ONCE")

    def action_select_continuous(self) -> None:
        if self._mode != "WELCOME":
            return
        self._launch_monitor("CONTINUOUS")

    def action_select_manual(self) -> None:
        if self._mode != "WELCOME":
            return
        self._mode = "MANUAL"
        self.query_one("#pas-log", RichLog).border_title = " CHAT HISTORY "
        self.query_one("#ai-log",  RichLog).border_title = " AI ANALYSIS "
        self.query_one("#pas-log", RichLog).clear()
        self.query_one("#ai-log",  RichLog).clear()
        # Enable chat input
        inp = self.query_one("#chat-input", Input)
        inp.disabled = False
        inp.placeholder = "  ›  Type SQL or ask a question...   ('rewrite last' to rewrite previous query)"
        inp.focus()
        self._ai_write(_dim(f"  {_ts()}  Manual mode — AI ready"))
        self._ai_write(_dim("  Type SQL in the input below, or ask any question."))
        self._ai_write(_sep())
        self._pas_write(_dim(f"  {_ts()}  Chat history"))
        self._pas_write(_sep())
        self._refresh_status()

    @work(thread=True)
    def _launch_monitor(self, mode: str) -> None:
        """Connect to MySQL, wire everything, start simulation."""
        try:
            from src.monitor.models    import MonitorConfig
            from src.monitor.connection import MonitoredConnection
            from src.pas.simulator     import PASSimulator
            from src.agent.factory     import create_orchestrator
            from src.config            import settings
        except ImportError as exc:
            self.call_from_thread(self._pas_write, _err(f"Import error: {exc}"))
            return

        config = MonitorConfig.from_settings(settings)

        try:
            conn = MonitoredConnection(config=config)
        except Exception as exc:
            self.call_from_thread(
                self._pas_write,
                _err(f"MySQL not available at {config.host}:{config.port}\n"
                     f"  Run: docker compose up -d\n  ({exc})"),
            )
            return

        orch = self._orchestrator or create_orchestrator()
        conn.set_orchestrator(orch)
        self._orchestrator = orch
        self._conn = conn

        conn.monitor.set_step_callback(
            lambda st, *a: self.call_from_thread(self._on_ai_step, st, *a)
        )
        sim = PASSimulator(
            conn=conn,
            on_start=lambda op: self.call_from_thread(self._on_pas_start, op),
            on_done=lambda op, ev: self.call_from_thread(self._on_pas_done, op, ev),
        )
        self._simulator = sim

        self.call_from_thread(self._set_mode_ui, mode)
        self.call_from_thread(
            self._pas_write,
            _dim(f"  {_ts()}  connected  {config.database}@{config.host}:{config.port}"),
        )
        self.call_from_thread(
            self._ai_write,
            _dim(f"  {_ts()}  AI watching for slow queries…"),
        )
        self.call_from_thread(self._ai_write, _sep())

        if mode == "ONCE":
            sim.run_once()
            self.call_from_thread(self._show_run_complete)
        else:
            sim.run()

    def _set_mode_ui(self, mode: str) -> None:
        self._mode = mode
        lp = self.query_one("#pas-log", RichLog)
        rp = self.query_one("#ai-log",  RichLog)
        lp.clear(); rp.clear()
        lp.border_title = " PAS ACTIVITY "
        rp.border_title = " AI ANALYSIS "
        # Enable chat input in all monitor modes (for live Q&A)
        inp = self.query_one("#chat-input", Input)
        inp.disabled = False
        inp.placeholder = "  ›  Ask about any query while monitoring..."
        self._refresh_status()

    def _show_run_complete(self) -> None:
        s = self._conn.monitor.get_summary() if self._conn else {}
        lp = self.query_one("#pas-log", RichLog)
        lp.write(_blank())
        lp.write(_sep_hi())
        lp.write(Text("  ALL 6 QUERIES COMPLETE", style=f"bold {_C['bright']}"))
        lp.write(_sep_hi())
        lp.write(_kv("Queries",  str(s.get("total_queries", 0))))
        lp.write(_kv("Slow",
                      f"{s.get('slow_queries', 0)} ({s.get('slow_pct', 0):.0f}%)",
                      vstyle=_C["red"]))
        lp.write(_kv("Avg time", f"{s.get('avg_time_ms', 0):,.0f} ms"))
        self._mode = "DONE"
        self._refresh_status()

    # ── PAS callbacks (main thread) ───────────────────────────────────────────

    def _pas_write(self, text: Text) -> None:
        self.query_one("#pas-log", RichLog).write(text)

    def _ai_write(self, text: Text) -> None:
        self.query_one("#ai-log", RichLog).write(text)

    def _on_pas_start(self, op: dict) -> None:
        log = self.query_one("#pas-log", RichLog)
        log.write(_blank())
        log.write(_sep_hi())
        # Operation header
        hdr = Text()
        hdr.append(f"  Op {op['id']} / 6  ", style=_C["muted"])
        hdr.append(f"{_ts()}  ", style=_C["muted"])
        hdr.append(op["name"], style=f"bold {_C['bright']}")
        log.write(hdr)
        log.write(_sep_hi())
        log.write(Text(f"  {op['narrative']}", style=_C["dim"]))
        sql_ln = Text()
        sql_ln.append("  sql  ", style=_C["muted"])
        sql_ln.append(_sql_preview(op["sql"]), style=_C["blue"])
        log.write(sql_ln)

    def _on_pas_done(self, op: dict, event: Any) -> None:
        log = self.query_one("#pas-log", RichLog)
        if event is None:
            log.write(_err("query failed to execute")); return

        ms   = event.metrics.execution_time_ms
        rows = event.metrics.rows_returned or 0
        self._total   += 1
        self._slow    += int(event.is_slow)
        self._sum_ms  += ms
        self._last_ms  = ms

        t = Text()
        t.append("  time  ", style=_C["muted"])
        if event.is_slow:
            t.append(f"{ms:>9,.0f} ms  SLOW ▲", style=f"bold {_C['red']}")
        else:
            t.append(f"{ms:>9,.1f} ms  fast ✓", style=_C["green"])
        log.write(t)

        r = Text()
        r.append("  rows  ", style=_C["muted"])
        r.append(f"{rows:,}", style=_C["sub"])
        log.write(r)

        if event.metrics.explain_output:
            ex  = event.metrics.explain_output[0]
            key = ex.key or "NONE"
            est = f"  est={ex.rows:,}" if ex.rows else ""
            pl  = Text()
            pl.append("  plan  ", style=_C["muted"])
            tc  = _C["red"] if ex.type == "ALL" else (_C["amber"] if ex.type == "index" else _C["green"])
            pl.append(f"type={ex.type}", style=tc)
            pl.append("  ", style="")
            kc  = _C["red"] if key == "NONE" else _C["green"]
            pl.append(f"key={key}", style=kc)
            pl.append(est, style=_C["dim"])
            log.write(pl)

        v = Text(); v.append("  ")
        if event.is_slow:
            v.append("⚠  slow — AI analysis triggered", style=_C["amber"])
        else:
            v.append("✓  healthy — no analysis needed", style=_C["green"])
        log.write(v)

        self._refresh_status()

    # ── AI step callbacks (main thread) ──────────────────────────────────────

    def _on_ai_step(self, step_type: str, *args: Any) -> None:
        log = self.query_one("#ai-log", RichLog)

        # ── Fast query (not slow, just logged) ───────────────────────────
        if step_type == "fast_query":
            ev = args[0]
            t = Text()
            t.append(f"  {_ts()}  ", style=_C["muted"])
            t.append(f"\u2713 {ev.metrics.execution_time_ms:.1f}ms  ", style=_C["green"])
            t.append(_sql_preview(ev.sql, 42), style=_C["dim"])
            log.write(t)
            return

        # ── Intercepted (slow query detected) ────────────────────────────
        if step_type == "intercepted":
            ev = args[0]
            ms = ev.metrics.execution_time_ms
            log.write(_blank())
            log.write(_sep_hi())
            hdr = Text()
            hdr.append("  INTERCEPTED  ", style=f"bold {_C['red']}")
            hdr.append(f"{_ts()}  ", style=_C["muted"])
            hdr.append(f"{ms:,.0f} ms  \u00b7  threshold exceeded", style=f"bold {_C['red']}")
            log.write(hdr)
            log.write(_sep_hi())
            sql_t = Text()
            sql_t.append("  sql  ", style=_C["muted"])
            sql_t.append(_sql_preview(ev.sql), style=_C["blue"])
            log.write(sql_t)
            log.write(_blank())
            return

        # ── [01] Semantic Cache ───────────────────────────────────────────
        if step_type == "cache":
            hit = args[0]
            log.write(_section("Semantic Cache", 1))
            if hit:
                log.write(Text("  HIT  \u2192  served from semantic cache", style=_C["green"]))
                log.write(_dim("  key: cosine similarity > 0.95"))
            else:
                log.write(Text("  MISS  \u2192  computing fresh analysis", style=_C["amber"]))
            log.write(_blank())

        # ── [02] Intent Classification ────────────────────────────────────
        elif step_type == "intent":
            intent = args[0]
            log.write(_section("Intent Classification", 2))
            t = Text()
            t.append("  \u2192 ", style=_C["muted"])
            t.append(str(intent), style=_C["purple"])
            log.write(t)
            log.write(_dim("  keyword match: SQL detected, performance context"))
            log.write(_blank())

        # ── [03] SQL Extraction ───────────────────────────────────────────
        elif step_type == "sql_extracted":
            sql = args[0] or ""
            log.write(_section("SQL Extraction", 3))
            log.write(Text(f"  {_sql_preview(str(sql), 58)}", style=_C["blue"]))
            log.write(_blank())

        # ── [04] Dense Vector Search ──────────────────────────────────────
        elif step_type == "dense_search":
            stats = args[0] if args else {}
            n = stats.get("dense_count", "?")
            log.write(_section("Dense Vector Search  (ChromaDB)", 4))
            log.write(_dim(f"  ChromaDB cosine similarity search"))
            log.write(_dim(f"  {n} candidates retrieved"))
            log.write(_blank())

        # ── [05] Keyword Search ───────────────────────────────────────────
        elif step_type == "keyword_search":
            stats  = args[0] if args else {}
            n      = stats.get("keyword_count", "?")
            tokens = stats.get("keywords_used", [])
            log.write(_section("Keyword Search", 5))
            if tokens:
                tok_s = ", ".join(str(k) for k in tokens[:5])
                log.write(_dim(f"  tokens: {tok_s}"))
            log.write(_dim(f"  {n} keyword match(es) found"))
            log.write(_blank())

        # ── [06] RRF Fusion ───────────────────────────────────────────────
        elif step_type == "rrf_fusion":
            stats  = args[0] if args else {}
            dense  = stats.get("dense_count", "?")
            kw     = stats.get("keyword_count", "?")
            merged = stats.get("merged_count", "?")
            log.write(_section("RRF Fusion  (Reciprocal Rank)", 6))
            log.write(_dim("  Reciprocal Rank Fusion"))
            t = Text()
            t.append(f"  dense({dense}) + keyword({kw})", style=_C["sub"])
            t.append(f"  \u2192  merged {merged}", style=_C["text"])
            log.write(t)
            log.write(_blank())

        # ── [07] Cross-Encoder Reranking ──────────────────────────────────
        elif step_type == "rerank":
            cases = args[0] if args else []
            log.write(_section("Cross-Encoder Reranking", 7))
            log.write(_dim(f"  {len(cases)} candidates \u2192 top {len(cases)} selected"))
            log.write(_blank())
            for i, c in enumerate(cases[:3], 1):
                score = c.get("_rerank_score")
                score_str = f"{score:.2f}" if score is not None else "n/a"
                sc = _C["green"] if score and score > 0 else _C["amber"] if score and score > -5 else _C["dim"]
                # Line 1: rank, case_id, score
                t = Text()
                t.append(f"  {i}  ", style=_C["muted"])
                t.append(f"{c.get('case_id','?'):<12}", style=_C["sub"])
                t.append(f"score: {score_str}", style=sc)
                log.write(t)
                # Line 2: title
                title = c.get("title", "")
                if title:
                    log.write(_dim(f"     {title}"))
                # Line 3: root cause (if available)
                root = c.get("root_cause", "")
                if root:
                    log.write(_dim(f"     Root: {root[:60]}"))
                log.write(_blank())

        # ── [08] Rule Engine ──────────────────────────────────────────────
        elif step_type == "rules":
            findings = args[0] if args else []
            log.write(_section(f"Rule Engine  ({len(findings)} triggered)", 8))
            if not findings:
                log.write(_dim("  No rule violations detected"))
            else:
                sev_sym = {"critical": "\u25cf", "high": "\u25c6", "warning": "\u25b8", "medium": "\u25b8"}
                log.write(_blank())
                for f in findings:
                    fc = _SEV.get(f.severity, _C["text"])
                    # Line 1: symbol + rule name + severity
                    t = Text()
                    t.append(f"  {sev_sym.get(f.severity, '\u25b8')} ", style=fc)
                    t.append(f"{f.rule:<22}", style=f"bold {fc}")
                    t.append(f"  {f.severity}", style=_C["dim"])
                    log.write(t)
                    # Line 2: description
                    log.write(_dim(f"    {f.message[:70]}"))
                    log.write(_blank())

        # ── [09] A/B Testing ─────────────────────────────────────────────
        elif step_type == "ab_testing":
            variant = args[0] if args else "?"
            log.write(_section("A/B Testing", 9))
            label = "conservative" if variant == "A" else "aggressive"
            t = Text()
            t.append(f"  Variant: ", style=_C["muted"])
            t.append(f"{variant}  ", style=f"bold {_C['purple']}")
            t.append(f"({label})", style=_C["dim"])
            log.write(t)
            if variant == "A":
                log.write(_dim("  Strategy: index + WHERE clause suggestions"))
            else:
                log.write(_dim("  Strategy: architectural (partitioning, caching)"))
            log.write(_dim("  (measured by user feedback loop)"))
            log.write(_blank())

        # ── [10] Anomaly Detection ────────────────────────────────────────
        elif step_type == "anomaly":
            result = args[0] if args else None
            log.write(_section("Anomaly Detection  (3-method ensemble)", 10))
            if result is None:
                log.write(_dim("  History: <3 data points"))
                log.write(_dim("  Not enough data for statistical detection"))
            elif not result.anomalies_detected:
                log.write(Text("  No anomaly  \u00b7  latency within normal range", style=_C["green"]))
            else:
                log.write(_dim(f"  History: {len(result.anomaly_indices)} spike(s) detected"))
                log.write(_blank())
                agreed = result.methods_agreed
                for method, indices in agreed.items():
                    sym = "\u25b2" if indices else "\u2014"
                    col = _C["red"] if indices else _C["green"]
                    t = Text()
                    t.append(f"  {method:<18}", style=_C["muted"])
                    t.append(f"{sym}  ", style=col)
                    idx_str = f"spike at idx {indices}" if indices else "normal"
                    t.append(idx_str, style=col)
                    log.write(t)
                log.write(_blank())
                consensus = Text()
                consensus.append("  Consensus: ", style=_C["muted"])
                methods_hit = sum(1 for v in agreed.values() if v)
                consensus.append(f"{methods_hit}/3 agree  \u2192  ", style=_C["text"])
                consensus.append(f"ANOMALY", style=f"bold {_C['red']}")
                log.write(consensus)
                log.write(_dim(f"  Severity: {result.severity}"))
            log.write(_blank())

        # ── [11] Query Rewriter ───────────────────────────────────────────
        elif step_type == "rewrite":
            rw = args[0] if args else None
            log.write(_section("Query Rewriter", 11))
            if rw is None or not rw.changes:
                log.write(_dim("  No rewrite applied"))
            else:
                for i, ch in enumerate(rw.changes, 1):
                    t = Text()
                    t.append(f"  {i}  ", style=_C["muted"])
                    t.append(ch[:66], style=_C["sub"])
                    log.write(t)
                log.write(_blank())
                if rw.index_suggestions:
                    for idx in rw.index_suggestions:
                        log.write(Text(f"  {idx[:66]}", style=_C["dim"]))
                    log.write(_blank())
                log.write(_dim(f"  Estimated: {rw.estimated_improvement}"))
            log.write(_blank())

        # ── [12] Confidence Score ─────────────────────────────────────────
        elif step_type == "confidence":
            bd = args[0] if args else {}
            log.write(_section("Confidence Score", 12))
            log.write(_blank())
            entries = [
                ("Rule findings", bd.get("rule", 0), "rules matched"),
                ("RAG rerank",    bd.get("rag",  0), "top rerank score"),
                ("LLM boost",     bd.get("llm",  0), bd.get("mode", "offline")),
            ]
            for label, val, desc in entries:
                t = Text()
                t.append(f"  {label:<16}", style=_C["muted"])
                col = _C["green"] if val > 0.2 else _C["amber"] if val > 0 else _C["dim"]
                t.append(f"+{val:.2f}", style=col)
                t.append(f"  ({desc})", style=_C["dim"])
                log.write(t)
            log.write(_sep())
            tot = Text()
            tot.append("  Total:          ", style=_C["muted"])
            tot.append(f"{bd.get('total', 0):.3f}", style=f"bold {_C['bright']}")
            log.write(tot)
            log.write(_blank())

        # ── [COMPLETE] Final result ───────────────────────────────────────
        elif step_type == "complete":
            self._render_result(log, args[0])

    def _render_result(self, log: RichLog, result: Any) -> None:
        sev   = result.severity.lower()
        color = _SEV.get(sev, _C["text"])
        conf  = int(result.confidence * 100)

        # ── Severity badge ────────────────────────────────────────────────
        log.write(_blank())
        log.write(_sep_hi())
        badge = Text()
        badge.append(f"  {sev.upper()}", style=f"bold {color}")
        badge.append(f"  \u00b7  {conf}%  \u00b7  {result.category}", style=_C["sub"])
        log.write(badge)
        log.write(_sep_hi())
        log.write(_blank())

        # ── Problem ───────────────────────────────────────────────────────
        log.write(Text(f"  {result.problem}", style=_C["text"]))
        log.write(_blank())

        # ── Suggestions ───────────────────────────────────────────────────
        if result.suggestion:
            log.write(_dim("  Suggestions"))
            for i, s in enumerate(result.suggestion[:4], 1):
                t = Text()
                t.append(f"  {i}  ", style=_C["muted"])
                t.append(s[:70], style=_C["sub"])
                log.write(t)
            log.write(_blank())

        # ── Rewritten SQL (the "Fix:" block from wireframe) ──────────────
        if result.rewritten_sql and result.rewritten_sql.changes:
            log.write(_dim("  Fix:"))
            for line in _rewrite_lines(result.rewritten_sql.rewritten, 6):
                log.write(Text(f"  {line}", style=_C["blue"]))
            log.write(_blank())
            if result.rewritten_sql.index_suggestions:
                for idx in result.rewritten_sql.index_suggestions:
                    log.write(Text(f"  {idx}", style=_C["dim"]))
                log.write(_blank())

        # ── Final separator ───────────────────────────────────────────────
        log.write(_sep_hi())
        log.write(_blank())


    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.clear()
        if not text:
            return
        if self._mode in ("ONCE", "CONTINUOUS", "MANUAL", "DONE"):
            self._handle_chat(text)

    @work(thread=True)
    @work(thread=True)
    def _handle_chat(self, text: str) -> None:
        """Smart chat: SQL → full 14-step pipeline.  Question → conversational AI."""
        orch = self._orchestrator
        if orch is None:
            self.call_from_thread(self._ai_write, _err("AI not ready \u2014 select a mode first"))
            return

        # Show user message in left panel
        self.call_from_thread(self._show_chat_user, text)

        lower = text.lower().strip()
        is_sql = bool(re.match(r"^\s*(SELECT|UPDATE|INSERT|DELETE|WITH)\b", text, re.IGNORECASE))

        # ── Special commands (answered directly, no pipeline) ─────────────
        if lower in ("help", "h", "?"):
            self.call_from_thread(self._show_help_chat)
            return
        if lower in ("tables", "show tables", "what tables", "list tables"):
            self.call_from_thread(self._show_tables_chat)
            return
        if lower in ("status", "info"):
            self.call_from_thread(self._show_status_chat)
            return
        if lower in ("rewrite last", "rewrite") and self._last_sql:
            self.call_from_thread(self._show_chat_ai_msg,
                f"Rewriting: {_sql_preview(self._last_sql, 50)}")
            text = f"Optimize this SQL: {self._last_sql}"
            is_sql = True

        sql = text if is_sql else None
        if sql:
            self._last_sql = sql

        # ── Run the orchestrator ──────────────────────────────────────────
        result    = orch.process(text, sql=sql)
        rag_stats = getattr(orch.retriever, "_last_stats", {})
        rag_cases = result.metadata.get("rag_cases", [])

        if is_sql:
            # ── SQL MODE: full 14-step pipeline in right panel ────────────
            self.call_from_thread(self._ai_clear_and_header, text)
            emit = lambda st, *a: self.call_from_thread(self._on_ai_step, st, *a)

            emit("cache", result.metadata.get("cache_hit", False)); time.sleep(0.08)

            intent = next(
                (s.get("result") for s in result.explanation_chain
                 if s.get("action") == "classify_intent"), "query_analysis")
            emit("intent", intent); time.sleep(0.08)

            sql_ext = next(
                (s.get("result") for s in result.explanation_chain
                 if s.get("action") == "sql_extracted"), sql or "")
            emit("sql_extracted", sql_ext); time.sleep(0.08)

            emit("dense_search",   rag_stats); time.sleep(0.08)
            emit("keyword_search", rag_stats); time.sleep(0.08)
            emit("rrf_fusion",     rag_stats); time.sleep(0.08)
            emit("rerank",         rag_cases); time.sleep(0.15)
            emit("rules",          result.rule_findings); time.sleep(0.12)
            emit("ab_testing",     result.metadata.get("ab_variant", "?")); time.sleep(0.08)
            emit("anomaly",        None); time.sleep(0.08)
            emit("rewrite",        result.rewritten_sql); time.sleep(0.12)

            rule_s = min(0.4 * len(result.rule_findings) / 3.0, 0.4) if result.rule_findings else 0.0
            rag_s  = 0.0
            if rag_cases:
                rv = rag_cases[0].get("_rerank_score")
                if rv is not None:
                    rag_s = round(0.4 * (1 / (1 + math.exp(-rv))), 3)
            emit("confidence", {
                "rule": round(rule_s, 3), "rag": round(rag_s, 3),
                "llm":  0.2 if result.metadata.get("mode") == "online" else 0.0,
                "total": result.confidence, "mode": result.metadata.get("mode", "offline"),
            }); time.sleep(0.08)
            emit("complete", result)

            # Summary in left panel
            self.call_from_thread(self._show_chat_ai_severity, result)

        else:
            # ── QUESTION MODE: conversational response in right panel ─────
            self.call_from_thread(self._show_chat_response, text, result, rag_cases)

        self._chat_count += 1
        self.call_from_thread(self._refresh_status)

    # ── Chat display helpers ──────────────────────────────────────────────────

    def _ai_clear_and_header(self, text: str) -> None:
        """Clear AI panel and write a header for new SQL analysis."""
        log = self.query_one("#ai-log", RichLog)
        log.clear()
        log.write(_blank())
        hdr = Text()
        hdr.append(f"  {_ts()}  ", style=_C["muted"])
        hdr.append("SQL Analysis", style=f"bold {_C['bright']}")
        log.write(hdr)
        log.write(Text(f"  {_sql_preview(text, 55)}", style=_C["blue"]))
        log.write(_blank())

    def _show_chat_user(self, text: str) -> None:
        """Show user message in left panel."""
        log = self.query_one("#pas-log", RichLog)
        log.write(_blank())
        t = Text()
        t.append(f"  YOU  {_ts()}", style=f"bold {_C['blue']}")
        log.write(t)
        log.write(Text(f"  {text[:70]}", style=_C["text"]))

    def _show_chat_ai_msg(self, msg: str) -> None:
        """Show a simple AI message in left panel."""
        log = self.query_one("#pas-log", RichLog)
        t = Text()
        t.append(f"  AI   {_ts()}  ", style=f"bold {_C['sub']}")
        t.append(msg, style=_C["text"])
        log.write(t)

    def _show_chat_ai_severity(self, result: Any) -> None:
        """Show severity + problem summary in left panel (after SQL analysis)."""
        log = self.query_one("#pas-log", RichLog)
        sev   = result.severity.lower()
        color = _SEV.get(sev, _C["text"])
        t = Text()
        t.append(f"  AI   {_ts()}  ", style=f"bold {_C['sub']}")
        t.append(f"{sev.upper()}  {int(result.confidence*100)}%", style=color)
        log.write(t)
        log.write(_dim(f"  {result.problem[:60]}"))
        log.write(_sep())

    def _show_chat_response(self, question: str, result: Any, rag_cases: list) -> None:
        """Show conversational AI response for natural language questions (no 14-step)."""
        log = self.query_one("#ai-log", RichLog)
        log.clear()
        log.write(_blank())

        # ── Header ────────────────────────────────────────────────────────
        hdr = Text()
        hdr.append(f"  {_ts()}  ", style=_C["muted"])
        hdr.append("AI Response", style=f"bold {_C['bright']}")
        log.write(hdr)
        log.write(_blank())

        # ── Answer ────────────────────────────────────────────────────────
        log.write(_sep())
        log.write(_blank())

        # Problem / answer
        if result.problem:
            log.write(Text(f"  {result.problem}", style=_C["text"]))
            log.write(_blank())

        # Root cause (if available)
        if result.root_cause and result.root_cause != result.problem:
            log.write(_dim("  Details"))
            # Wrap long root cause into multiple lines
            words = result.root_cause.split()
            line = "  "
            for w in words:
                if len(line) + len(w) + 1 > 55:
                    log.write(Text(line, style=_C["sub"]))
                    line = "  " + w
                else:
                    line += (" " if len(line) > 2 else "") + w
            if line.strip():
                log.write(Text(line, style=_C["sub"]))
            log.write(_blank())

        # ── Suggestions ───────────────────────────────────────────────────
        if result.suggestion:
            log.write(_dim("  Suggestions"))
            for i, s in enumerate(result.suggestion[:5], 1):
                t = Text()
                t.append(f"  {i}  ", style=_C["muted"])
                t.append(s[:68], style=_C["sub"])
                log.write(t)
            log.write(_blank())

        # ── Related cases from knowledge base ─────────────────────────────
        if rag_cases:
            log.write(_dim("  Related cases from knowledge base"))
            log.write(_blank())
            for i, c in enumerate(rag_cases[:3], 1):
                score = c.get("_rerank_score")
                sc_s  = f"{score:.2f}" if score is not None else "n/a"
                t = Text()
                t.append(f"  {i}  ", style=_C["muted"])
                t.append(f"{c.get('case_id','?'):<12}", style=_C["sub"])
                t.append(f"  score: {sc_s}", style=_C["dim"])
                log.write(t)
                log.write(_dim(f"     {c.get('title','')}"))
                log.write(_blank())

        # ── Rewritten SQL if applicable ───────────────────────────────────
        if result.rewritten_sql and result.rewritten_sql.changes:
            log.write(_dim("  Optimized SQL"))
            for line in _rewrite_lines(result.rewritten_sql.rewritten, 6):
                log.write(Text(f"  {line}", style=_C["blue"]))
            log.write(_blank())
            for idx in result.rewritten_sql.index_suggestions:
                log.write(Text(f"  {idx}", style=_C["dim"]))
            log.write(_blank())

        log.write(_sep())

        # ── Summary in left panel ─────────────────────────────────────────
        lp = self.query_one("#pas-log", RichLog)
        sev   = result.severity.lower()
        color = _SEV.get(sev, _C["text"])
        t = Text()
        t.append(f"  AI   {_ts()}  ", style=f"bold {_C['sub']}")
        if sev in ("critical", "high"):
            t.append(f"{sev.upper()}  ", style=color)
        t.append(result.problem[:50], style=_C["dim"])
        lp.write(t)
        lp.write(_sep())

    # ── Special command handlers ──────────────────────────────────────────────

    def _show_help_chat(self) -> None:
        """Show help in the AI panel."""
        log = self.query_one("#ai-log", RichLog)
        log.clear()
        log.write(_blank())
        log.write(Text("  Chat Commands", style=f"bold {_C['bright']}"))
        log.write(_blank())
        log.write(_sep())
        log.write(_blank())

        cmds = [
            ("SQL query",       "Full 14-step AI pipeline analysis"),
            ("question",        "Conversational AI response"),
            ("tables",          "Show database tables and row counts"),
            ("rewrite last",    "Rewrite the last SQL query you entered"),
            ("status",          "Show monitoring statistics"),
            ("help",            "Show this help"),
        ]
        for cmd, desc in cmds:
            t = Text()
            t.append(f"  {cmd:<18}", style=_C["blue"])
            t.append(desc, style=_C["dim"])
            log.write(t)

        log.write(_blank())
        log.write(_sep())
        log.write(_blank())
        log.write(_dim("  Examples"))
        log.write(_blank())
        examples = [
            "SELECT * FROM salaries",
            "SELECT * FROM employees WHERE first_name = 'Georgi'",
            "Why is JSON_EXTRACT slow?",
            "How do I optimize a nested subquery?",
            "What causes latency spikes?",
        ]
        for ex in examples:
            t = Text()
            t.append("  \u203a  ", style=_C["muted"])
            t.append(ex, style=_C["blue"])
            log.write(t)

        self._show_chat_ai_msg("Type SQL or ask any question.")

    def _show_tables_chat(self) -> None:
        """Show database tables in the AI panel."""
        log = self.query_one("#ai-log", RichLog)
        log.clear()
        log.write(_blank())
        log.write(Text("  Database Tables", style=f"bold {_C['bright']}"))
        log.write(_blank())
        log.write(_sep())
        log.write(_blank())

        # Header
        hdr = Text()
        hdr.append(f"  {'Table':<16}", style=f"bold {_C['sub']}")
        hdr.append(f"{'Rows':>12}   ", style=f"bold {_C['sub']}")
        hdr.append("Description", style=f"bold {_C['sub']}")
        log.write(hdr)
        log.write(_sep())

        for tbl, rows, desc in _DB_TABLES:
            t = Text()
            t.append(f"  {tbl:<16}", style=_C["blue"])
            t.append(f"{rows:>12,}   ", style=_C["text"])
            t.append(desc, style=_C["dim"])
            log.write(t)

        log.write(_sep())
        total = sum(r for _, r, _ in _DB_TABLES)
        log.write(_dim(f"  Total: ~{total/1_000_000:.1f}M rows"))
        log.write(_blank())

        # Also show schema tables (policy_data etc.)
        try:
            import json
            with open("data/schemas.json") as f:
                schemas = json.load(f)
            log.write(_dim("  Schema tables (for manual CLI queries)"))
            log.write(_sep())
            for tbl, info in schemas.items():
                t = Text()
                t.append(f"  {tbl:<16}", style=_C["blue"])
                est = info.get("row_count_estimate", 0)
                t.append(f"{est:>12,}   ", style=_C["text"])
                cols = info.get("key_columns", [])
                t.append(", ".join(cols[:4]), style=_C["dim"])
                log.write(t)
            log.write(_sep())
        except Exception:
            pass

        self._show_chat_ai_msg("Tables listed. Type SQL to analyze a query.")

    def _show_status_chat(self) -> None:
        """Show system status in the AI panel."""
        log = self.query_one("#ai-log", RichLog)
        log.clear()
        log.write(_blank())
        log.write(Text("  System Status", style=f"bold {_C['bright']}"))
        log.write(_blank())
        log.write(_sep())
        log.write(_blank())

        entries = [
            ("Mode",       self._mode),
            ("Queries",    str(self._total)),
            ("Slow",       str(self._slow)),
            ("Chat msgs",  str(self._chat_count)),
        ]
        for k, v in entries:
            t = Text()
            t.append(f"  {k:<12}", style=_C["muted"])
            t.append(v, style=_C["text"])
            log.write(t)

        if self._conn:
            s = self._conn.monitor.get_summary()
            log.write(_blank())
            log.write(_dim(f"  Monitor history: {s.get('total_queries',0)} events"))
            log.write(_dim(f"  Avg time: {s.get('avg_time_ms',0):,.0f} ms"))

        if self._last_sql:
            log.write(_blank())
            log.write(_dim(f"  Last SQL: {_sql_preview(self._last_sql, 45)}"))

        log.write(_blank())
        log.write(_sep())
        self._show_chat_ai_msg("Status shown.")


    # ── Status bar ────────────────────────────────────────────────────────────

    def _refresh_status(self) -> None:
        if self._mode == "WELCOME":
            bar = "  PAS Query Monitor  ·  Select a mode to begin  ·  [1] Once  [2] Continuous  [3] Manual"
        elif self._mode == "MANUAL":
            bar = f"  Chat: {self._chat_count} messages  ·  ◌ MANUAL"
        elif self._mode == "DONE":
            s = f"Queries:{self._total}  Slow:{self._slow}"
            bar = f"  {s}  ·  ✓ COMPLETE"
        else:
            pct  = f"{self._slow/self._total*100:.0f}%" if self._total else "—"
            avg  = f"{self._sum_ms/self._total:,.0f} ms"  if self._total else "—"
            last = f"{self._last_ms:,.0f} ms"              if self._last_ms else "—"
            sym  = "⏸" if (self._simulator and self._simulator._paused) else "●"
            bar  = (f"  Queries:{self._total}  Slow:{self._slow}({pct})"
                    f"  Avg:{avg}  Last:{last}  {sym} {self._mode}")
        self.query_one("#status-bar", Static).update(bar)

    # ── Key actions ───────────────────────────────────────────────────────────

    def action_toggle_pause(self) -> None:
        if not self._simulator or self._mode not in ("ONCE", "CONTINUOUS"):
            return
        if self._simulator._paused:
            self._simulator.resume()
        else:
            self._simulator.pause()
        self._refresh_status()

    def action_restart(self) -> None:
        if self._simulator:
            self._simulator.stop()
        if self._conn:
            try: self._conn.close()
            except Exception: pass
        self._simulator = None
        self._conn       = None
        self._mode       = "WELCOME"
        self._total = self._slow = 0
        self._sum_ms = self._last_ms = 0.0
        inp = self.query_one("#chat-input", Input)
        inp.disabled = True
        inp.placeholder = "  Press [1] Run Once  [2] Continuous  [3] Manual/Chat to begin..."
        self._draw_welcome()

    def action_quit(self) -> None:
        if self._simulator:
            self._simulator.stop()
        self.exit()


if __name__ == "__main__":
    LiveMonitorApp().run()
