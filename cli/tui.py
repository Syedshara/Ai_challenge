"""Full-screen Textual TUI for the Query Intelligence Engine."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure project root on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.utils.silence import suppress_all
suppress_all()

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Header, Footer, Input, Static
from textual.binding import Binding
from textual import work

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.console import Group
from rich import box

from src.models import AnalysisResponse


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
        yield Input(
            placeholder="Ask about SQL performance, or paste SQL...",
            id="query-input",
        )
        yield Footer()

    def on_mount(self) -> None:
        from src.agent.factory import create_orchestrator

        self.orchestrator = create_orchestrator()

        try:
            from src.config import settings
            kb_path = Path(settings.knowledge_base_path)
            self.cases = json.loads(kb_path.read_text()) if kb_path.exists() else []
        except Exception:
            self.cases = []

        self._update_subtitle()

    # ── Input handling ──────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        event.input.clear()

        # Command dispatch
        lower = query.lower()
        if lower in ("help", "h", "?"):
            self.action_show_help()
            return
        if lower in ("cases", "case"):
            self.action_show_cases()
            return
        if lower in ("anomaly", "anomalies"):
            self.action_run_anomaly()
            return
        if lower in ("status", "info"):
            self.action_show_status()
            return
        if lower in ("stats", "feedback"):
            self.action_show_stats()
            return

        # Case number shortcut
        if query.isdigit() and 1 <= int(query) <= len(self.cases):
            case = self.cases[int(query) - 1]
            sql = case.get("query")
            user_query = case.get("problem") or case.get("title", query)
            self._mount_user_panel(user_query)
            loading = Static("[bold green]Analyzing...[/bold green]")
            self.query_one("#output").mount(loading)
            loading.scroll_visible()
            self._run_analysis(user_query, sql=sql, loading_widget=loading)
            return

        # Normal query
        self._mount_user_panel(query)
        loading = Static("[bold green]Analyzing...[/bold green]")
        self.query_one("#output").mount(loading)
        loading.scroll_visible()
        self._run_analysis(query, sql=None, loading_widget=loading)

    def _mount_user_panel(self, query: str) -> None:
        panel = Panel(query, title="YOU", border_style="blue")
        self.query_one("#output").mount(Static(panel))

    # ── Background analysis ─────────────────────────────────────────────────

    @work(thread=True)
    def _run_analysis(
        self, query: str, sql: str | None, loading_widget: Static
    ) -> None:
        try:
            response = self.orchestrator.process(query, sql=sql)
            renderable = self._build_response_panel(response)
            self.call_from_thread(self._show_result, renderable, loading_widget)
        except Exception as exc:
            error_panel = Panel(
                f"[bold red]Error:[/bold red] {exc}",
                title="ERROR",
                border_style="red",
            )
            self.call_from_thread(self._show_result, error_panel, loading_widget)

    def _show_result(self, renderable, loading_widget: Static) -> None:
        loading_widget.remove()
        widget = Static(renderable)
        self.query_one("#output").mount(widget)
        widget.scroll_visible()
        self._update_subtitle()

    # ── Response panel builder ──────────────────────────────────────────────

    def _build_response_panel(self, response: AnalysisResponse):
        """Build a Rich Panel from an AnalysisResponse."""
        parts = []
        sev = response.severity.lower()
        conf_pct = int(response.confidence * 100)

        # Severity-based colors
        if sev == "critical":
            sev_color = "red"
        elif sev == "high":
            sev_color = "yellow"
        else:
            sev_color = "green"

        # 1. Severity header
        header = Text()
        header.append(
            f"{response.category.upper()} ", style=f"bold {sev_color}"
        )
        header.append("  Severity: ", style="dim")
        header.append(response.severity.upper(), style=f"bold {sev_color}")
        header.append("  Confidence: ", style="dim")
        header.append(f"{conf_pct}%", style=f"bold {sev_color}")
        parts.append(header)

        # 2. Problem
        prob_text = Text()
        prob_text.append("PROBLEM\n", style="bold red")
        prob_text.append(response.problem)
        parts.append(prob_text)

        # 3. Root cause
        rc_text = Text()
        rc_text.append("ROOT CAUSE\n", style="bold")
        rc_text.append(response.root_cause)
        parts.append(rc_text)

        # 4. Rule findings table
        if response.rule_findings:
            rt = Table(
                title="Rule Findings", box=box.SIMPLE, title_style="bold yellow"
            )
            rt.add_column("Rule", style="cyan")
            rt.add_column("Severity", style="yellow")
            rt.add_column("Fix")
            for f in response.rule_findings:
                rt.add_row(f.rule, f.severity, f.fix)
            parts.append(rt)

        # 5. Suggestions
        if response.suggestion:
            sug_lines = []
            for i, s in enumerate(response.suggestion, 1):
                sug_lines.append(f"  {i}. {s}")
            sug_text = Text()
            sug_text.append("SUGGESTIONS\n", style="bold green")
            sug_text.append("\n".join(sug_lines))
            parts.append(sug_text)

        # 6. Rewritten SQL
        if response.rewritten_sql and response.rewritten_sql.changes:
            rw = response.rewritten_sql
            rw_parts = [
                Panel(rw.rewritten, title="Rewritten SQL", border_style="cyan")
            ]
            if rw.index_suggestions:
                idx_text = Text()
                idx_text.append("Index Suggestions:\n", style="bold cyan")
                for idx in rw.index_suggestions:
                    idx_text.append(f"  - {idx}\n")
                rw_parts.append(idx_text)
            imp_text = Text()
            imp_text.append("Estimated improvement: ", style="dim")
            imp_text.append(rw.estimated_improvement, style="green")
            rw_parts.append(imp_text)
            parts.append(Group(*rw_parts))

        # 7. Similar cases (from RAG)
        rag_cases = response.metadata.get("rag_cases", [])
        if rag_cases:
            ct = Table(
                title="Similar Cases (RAG)",
                box=box.SIMPLE,
                title_style="bold magenta",
            )
            ct.add_column("#", style="dim", width=3)
            ct.add_column("Title")
            ct.add_column("Score", justify="right")
            ct.add_column("ID", style="dim")
            for i, c in enumerate(rag_cases, 1):
                rerank = c.get("_rerank_score")
                dist = c.get("_distance")
                if rerank is not None:
                    score = f"{rerank:.3f}"
                elif dist is not None:
                    score = f"{1.0 - dist:.3f}"
                else:
                    score = "n/a"
                ct.add_row(
                    str(i),
                    c.get("title", ""),
                    score,
                    c.get("case_id", ""),
                )
            parts.append(ct)

        # 8. Reasoning trace
        if response.explanation_chain:
            et = Table(
                title="Reasoning Trace",
                box=box.SIMPLE,
                title_style="bold blue",
            )
            et.add_column("#", style="dim", width=3)
            et.add_column("Step")
            et.add_column("Result")
            for i, step in enumerate(response.explanation_chain, 1):
                action = step.get("action") or step.get("tool") or step.get("finish_reason", "")
                result = step.get("result") or step.get("matches") or step.get("findings") or step.get("changes") or ""
                et.add_row(str(i), str(action), str(result))
            # Final row: mode + processing time
            mode = response.metadata.get("mode", "unknown")
            proc_ms = response.metadata.get("processing_time_ms", "?")
            et.add_row("", "mode", f"{mode} ({proc_ms}ms)")
            parts.append(et)

        # 9. Anomaly info
        if response.anomaly_info and response.anomaly_info.anomalies_detected:
            a = response.anomaly_info
            anom_text = Text()
            anom_text.append("ANOMALY DETECTED\n", style="bold red")
            anom_text.append(f"Severity: {a.severity}\n", style="red")
            anom_text.append(f"Anomaly indices: {a.anomaly_indices}\n")
            if a.methods_agreed:
                for method, indices in a.methods_agreed.items():
                    anom_text.append(f"  {method}: {indices}\n", style="dim")
            parts.append(anom_text)

        # Border color
        if sev == "critical":
            border = "red"
        elif sev == "high":
            border = "yellow"
        else:
            border = "green"

        return Panel(Group(*parts), title="ANALYSIS", border_style=border)

    # ── Subtitle ────────────────────────────────────────────────────────────

    def _update_subtitle(self) -> None:
        try:
            from src.config import settings

            mode = "Online (LLM)" if settings.llm_available else "Offline (Rules+RAG)"

            try:
                kb_path = Path(settings.knowledge_base_path)
                kb_count = len(json.loads(kb_path.read_text())) if kb_path.exists() else 0
            except Exception:
                kb_count = 0

            try:
                vec_count = self.orchestrator.retriever.vector_store.count()
            except Exception:
                vec_count = 0

            try:
                cache_count = self.orchestrator.cache.size()
            except Exception:
                cache_count = 0

            try:
                fb_path = Path(settings.feedback_log_path)
                fb_count = len(json.loads(fb_path.read_text())) if fb_path.exists() else 0
            except Exception:
                fb_count = 0

            self.sub_title = (
                f"{mode} | KB:{kb_count} | Vec:{vec_count} "
                f"| Cache:{cache_count} | Feedback:{fb_count}"
            )
        except Exception:
            self.sub_title = ""

    # ── Welcome text ────────────────────────────────────────────────────────

    def _welcome_text(self) -> str:
        return (
            "Welcome to Query Intelligence Engine\n"
            "Insurance PAS Performance Analyzer\n\n"
            "Ask anything about SQL performance, or type commands, "
            "or a number (1-10) for demo cases.\n\n"
            "Press F1 for help."
        )

    # ── F1: Help ────────────────────────────────────────────────────────────

    def action_show_help(self) -> None:
        help_text = Text()
        help_text.append("COMMANDS\n", style="bold cyan")
        help_text.append("  help, h, ?     Show this help\n")
        help_text.append("  cases, case    Browse knowledge base cases\n")
        help_text.append("  anomaly        Run anomaly detection on metrics\n")
        help_text.append("  status, info   Show system status\n")
        help_text.append("  stats          Show feedback & A/B stats\n")
        help_text.append("  1-10           Analyze a demo case by number\n")
        help_text.append("\n")
        help_text.append("EXAMPLE QUERIES\n", style="bold cyan")
        help_text.append("  Why is SELECT * FROM policy_data slow?\n")
        help_text.append("  JSON filter performance issue\n")
        help_text.append("  How to optimize this join query?\n")
        help_text.append("  Is this an anomaly? Latency jumped from 1s to 50s\n")
        help_text.append("\n")
        help_text.append("KEYBINDINGS\n", style="bold cyan")
        help_text.append("  F1  Help\n")
        help_text.append("  F2  Case Browser\n")
        help_text.append("  F3  Anomaly Detection\n")
        help_text.append("  F4  System Status\n")
        help_text.append("  F5  Feedback & A/B Stats\n")
        help_text.append("  Ctrl+C  Quit\n")

        panel = Panel(help_text, title="F1 -- Help", border_style="cyan")
        self.query_one("#output").mount(Static(panel))

    # ── F2: Case Browser ────────────────────────────────────────────────────

    def action_show_cases(self) -> None:
        from src.config import settings

        try:
            kb_path = Path(settings.knowledge_base_path)
            cases = json.loads(kb_path.read_text()) if kb_path.exists() else []
            self.cases = cases
        except Exception:
            cases = self.cases

        ct = Table(box=box.ROUNDED, title_style="bold")
        ct.add_column("#", style="dim", width=3)
        ct.add_column("Title", min_width=30)
        ct.add_column("Severity")
        ct.add_column("Category")
        ct.add_column("Exec Time", justify="right")

        sev_styles = {
            "critical": "bold red",
            "high": "bold yellow",
            "medium": "yellow",
            "low": "green",
        }

        for i, case in enumerate(cases, 1):
            sev = case.get("severity", "medium")
            sev_text = Text(sev.upper(), style=sev_styles.get(sev, "white"))
            exec_time = case.get("context", {}).get("execution_time", "")
            ct.add_row(
                str(i),
                case.get("title", "Untitled"),
                sev_text,
                case.get("category", ""),
                str(exec_time),
            )

        panel = Panel(ct, title="F2 -- Case Browser", border_style="magenta")
        output = self.query_one("#output")
        output.mount(Static(panel))
        hint = Static("[dim]Type a case number (1-10) to analyze it[/dim]")
        output.mount(hint)
        hint.scroll_visible()

    # ── F3: Anomaly Detection ───────────────────────────────────────────────

    def action_run_anomaly(self) -> None:
        from src.config import settings
        from src.anomaly.detector import AnomalyDetector

        try:
            metrics_path = Path(settings.metrics_path)
            if not metrics_path.exists():
                panel = Panel(
                    "[yellow]No metrics file found.[/yellow]",
                    title="F3 -- Anomaly Detection",
                    border_style="yellow",
                )
                self.query_one("#output").mount(Static(panel))
                return
            metrics_data = json.loads(metrics_path.read_text())
        except Exception as exc:
            panel = Panel(
                f"[red]Failed to load metrics: {exc}[/red]",
                title="F3 -- Anomaly Detection",
                border_style="red",
            )
            self.query_one("#output").mount(Static(panel))
            return

        detector = AnomalyDetector(
            zscore_threshold=settings.anomaly_zscore_threshold,
            iqr_factor=settings.anomaly_iqr_factor,
            window_size=settings.anomaly_window_size,
        )

        parts = []

        # Handle list of entries or single entry
        entries = metrics_data if isinstance(metrics_data, list) else [metrics_data]

        for idx, entry in enumerate(entries):
            metrics = entry.get("metrics", entry) if isinstance(entry, dict) else entry
            if isinstance(metrics, dict):
                metrics = [metrics]
            if not isinstance(metrics, list):
                continue

            result = detector.detect(metrics)

            mt = Table(
                title=f"Entry {idx + 1}",
                box=box.SIMPLE,
                title_style="bold",
            )
            mt.add_column("Method", style="cyan")
            mt.add_column("Anomaly Indices")

            methods = result.methods_agreed
            for method_name, indices in methods.items():
                mt.add_row(method_name, str(indices) if indices else "none")

            mt.add_row("", "")
            mt.add_row(
                "Consensus",
                str(result.anomaly_indices) if result.anomaly_indices else "none",
            )

            sev_color = "red" if result.severity in ("critical", "high") else "yellow" if result.severity == "medium" else "green"
            sev_text = Text()
            sev_text.append(f"Severity: {result.severity.upper()}", style=f"bold {sev_color}")
            sev_text.append(f" | Detected: {result.anomalies_detected}")

            if result.anomaly_points:
                values = [float(m.get("latency_ms", 0)) for m in metrics]
                normal = [v for i, v in enumerate(values) if i not in set(result.anomaly_indices)]
                if normal:
                    normal_mean = sum(normal) / len(normal)
                    for ai in result.anomaly_indices:
                        if ai < len(values):
                            ratio = values[ai] / normal_mean if normal_mean > 0 else 0
                            sev_text.append(f"\n  Index {ai}: {values[ai]:.0f}ms (spike ratio: {ratio:.1f}x)")

            parts.append(mt)
            parts.append(sev_text)
            parts.append(Text(""))

        panel = Panel(
            Group(*parts) if parts else Text("[green]No anomalies found.[/green]"),
            title="F3 -- Anomaly Detection (Live)",
            border_style="red" if any(
                e.get("metrics") or e for e in entries
            ) else "green",
        )
        widget = Static(panel)
        self.query_one("#output").mount(widget)
        widget.scroll_visible()

    # ── F4: Status ──────────────────────────────────────────────────────────

    def action_show_status(self) -> None:
        from src.config import settings

        try:
            kb_path = Path(settings.knowledge_base_path)
            kb_cases = len(json.loads(kb_path.read_text())) if kb_path.exists() else 0
        except Exception:
            kb_cases = 0

        try:
            vec_count = self.orchestrator.retriever.vector_store.count()
        except Exception:
            vec_count = 0

        try:
            schemas_path = Path(settings.schemas_path)
            schemas = json.loads(schemas_path.read_text()) if schemas_path.exists() else {}
            schema_count = len(schemas)
        except Exception:
            schema_count = 0

        try:
            patterns_path = Path(settings.patterns_path)
            patterns = json.loads(patterns_path.read_text()) if patterns_path.exists() else []
            rules_count = len(patterns) if isinstance(patterns, list) else len(patterns.get("rules", patterns.get("patterns", [])))
        except Exception:
            rules_count = 0

        try:
            metrics_path = Path(settings.metrics_path)
            metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else []
            metrics_count = len(metrics) if isinstance(metrics, list) else 1
        except Exception:
            metrics_count = 0

        try:
            fb_path = Path(settings.feedback_log_path)
            fb_count = len(json.loads(fb_path.read_text())) if fb_path.exists() else 0
        except Exception:
            fb_count = 0

        try:
            cache_count = self.orchestrator.cache.size()
        except Exception:
            cache_count = 0

        mode = "Online (LLM)" if settings.llm_available else "Offline (Rules+RAG)"
        model = settings.llm_model if settings.llm_available else "n/a"

        st = Table(box=box.ROUNDED)
        st.add_column("Data Source", style="cyan")
        st.add_column("Count", justify="right", style="green")
        st.add_column("Location", style="dim")

        st.add_row("Knowledge Base Cases", str(kb_cases), settings.knowledge_base_path)
        st.add_row("Vector Embeddings", str(vec_count), settings.chroma_persist_dir)
        st.add_row("Schema Tables", str(schema_count), settings.schemas_path)
        st.add_row("Query Rules/Patterns", str(rules_count), settings.patterns_path)
        st.add_row("Metrics Entries", str(metrics_count), settings.metrics_path)
        st.add_row("Feedback Entries", str(fb_count), settings.feedback_log_path)
        st.add_row("Cache Entries", str(cache_count), "(in-memory)")
        st.add_row("Mode", mode, "")
        st.add_row("LLM Model", model, settings.llm_base_url or "default")

        panel = Panel(st, title="F4 -- Status", border_style="blue")
        widget = Static(panel)
        self.query_one("#output").mount(widget)
        widget.scroll_visible()

    # ── F5: Feedback & A/B Stats ────────────────────────────────────────────

    def action_show_stats(self) -> None:
        from src.config import settings
        from src.learning.feedback_loop import FeedbackLoop
        from src.ab_testing.ab_engine import ABTestingEngine

        parts = []

        # Feedback stats
        try:
            fl = FeedbackLoop(
                feedback_log_path=settings.feedback_log_path,
                knowledge_base_path=settings.knowledge_base_path,
            )
            fb_stats = fl.get_stats()

            ft = Table(
                title="Feedback Summary",
                box=box.ROUNDED,
                title_style="bold green",
            )
            ft.add_column("Metric", style="cyan")
            ft.add_column("Value", justify="right", style="green")

            ft.add_row("Total Feedback", str(fb_stats.get("total", 0)))
            pos_rate = fb_stats.get("positive_rate", 0)
            ft.add_row("Positive Rate", f"{pos_rate * 100:.1f}%")
            ft.add_row("Cases Flagged", str(fb_stats.get("cases_flagged", 0)))

            flagged = fb_stats.get("flagged_cases", [])
            if flagged:
                ft.add_row("Flagged Case IDs", ", ".join(str(f) for f in flagged))

            parts.append(ft)
        except Exception as exc:
            parts.append(Text(f"Feedback stats error: {exc}", style="red"))

        # A/B testing results
        try:
            fb_path = Path(settings.feedback_log_path)
            feedback_data = json.loads(fb_path.read_text()) if fb_path.exists() else []

            ab = ABTestingEngine()
            ab_results = ab.get_results(feedback_data)

            at = Table(
                title="A/B Testing Results",
                box=box.ROUNDED,
                title_style="bold magenta",
            )
            at.add_column("Variant", style="cyan")
            at.add_column("Name")
            at.add_column("Queries", justify="right")
            at.add_column("Positive", justify="right")
            at.add_column("Win Rate", justify="right", style="green")

            for variant_key in ("variant_A", "variant_B"):
                v = ab_results.get(variant_key, {})
                label = variant_key[-1]
                at.add_row(
                    label,
                    v.get("name", ""),
                    str(v.get("queries", 0)),
                    str(v.get("positive_feedback", 0)),
                    f"{v.get('win_rate', 0) * 100:.1f}%",
                )

            parts.append(at)

            # Recommendation
            rec = Text()
            winner = ab_results.get("winner")
            if winner:
                rec.append(f"Winner: Variant {winner}", style="bold green")
            rec.append(f"\n{ab_results.get('recommendation', '')}", style="dim")
            rec.append(f"\nTotal queries: {ab_results.get('total_queries', 0)}", style="dim")
            parts.append(rec)

        except Exception as exc:
            parts.append(Text(f"A/B stats error: {exc}", style="red"))

        panel = Panel(
            Group(*parts),
            title="F5 -- Feedback & A/B Stats",
            border_style="magenta",
        )
        widget = Static(panel)
        self.query_one("#output").mount(widget)
        widget.scroll_visible()


if __name__ == "__main__":
    QueryIntelligenceApp().run()
