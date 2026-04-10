"""Rich interactive CLI for the Query Intelligence Engine."""
from __future__ import annotations

import json
import os
import sys

# ── Ensure project root is on sys.path regardless of how this file is invoked ──
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ── Silence noisy third-party warnings BEFORE any ML imports ──
from src.utils.silence import suppress_all
suppress_all()

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn
from rich import box
from rich.text import Text
from rich.prompt import Prompt

console = Console()

DEMO_QUERIES = [
    ("Why is this query slow?",
     "SELECT * FROM policy_data"),
    ("JSON filter performance issue",
     "SELECT * FROM policy_data WHERE JSON_EXTRACT(data, '$.policy.state') = 'CA'"),
    ("Complex join is slow",
     "SELECT p.policy_id, c.claim_amount FROM policy_data p "
     "JOIN claims_data c ON p.policy_id = c.policy_id "
     "JOIN config_table cfg ON cfg.key = 'rate' "
     "WHERE JSON_EXTRACT(p.data, '$.state') = 'CA'"),
    ("High frequency config lookup",
     "SELECT * FROM config_table WHERE key = 'rate_engine_config'"),
    ("Nested subquery slow",
     "SELECT * FROM claims_data WHERE policy_id IN "
     "(SELECT policy_id FROM policy_data WHERE state = 'CA')"),
    ("Aggregation performance",
     "SELECT state, COUNT(*) as total FROM policy_data GROUP BY state"),
    ("Audit log query",
     "SELECT * FROM audit_log WHERE created_date > '2024-01-01'"),
    ("Is this an anomaly? Latency jumped from 1s to 50s",
     None),
    ("How to optimize this update?",
     "UPDATE policy_data SET status = 'EXPIRED' WHERE created_date < '2020-01-01'"),
    ("What would you change in the system design for production scale?",
     None),
]

SEVERITY_COLORS = {
    "critical": "bold red",
    "high": "bold yellow",
    "medium": "yellow",
    "low": "green",
    "none": "dim",
}


def _render_response(response, query: str, show_rewrite: bool = False) -> None:
    """Render an AnalysisResponse to the terminal using Rich."""
    sev = response.severity.lower()
    color = SEVERITY_COLORS.get(sev, "white")

    # ── Header panel ────────────────────────────────────────────────────────
    header = Text()
    header.append(f"🔴 " if sev == "critical" else "🟡 " if sev in ("high", "medium") else "🟢 ")
    header.append(f"[{response.category.upper()}]  ", style="bold dim")
    header.append(f"Severity: ", style="dim")
    header.append(response.severity.upper(), style=color)

    console.print(Panel(header, box=box.ROUNDED, border_style="dim"))

    # ── Problem ─────────────────────────────────────────────────────────────
    console.print(f"\n[bold red]🔴 Problem[/bold red]")
    console.print(f"   {response.problem}\n")

    # ── Root Cause ──────────────────────────────────────────────────────────
    console.print(f"[bold]📋 Root Cause[/bold]")
    console.print(f"   {response.root_cause}\n")

    # ── Suggestions ─────────────────────────────────────────────────────────
    console.print(f"[bold green]✅ Suggestions[/bold green]")
    for i, s in enumerate(response.suggestion[:6], 1):
        console.print(f"   [green]{i}.[/green] {s}")
    console.print()

    # ── Confidence bar ──────────────────────────────────────────────────────
    pct = int(response.confidence * 100)
    filled = int(response.confidence * 20)
    bar = "█" * filled + "░" * (20 - filled)
    console.print(f"[bold]📊 Confidence:[/bold]  [{bar}] {pct}%")

    # ── Similar cases ───────────────────────────────────────────────────────
    if response.similar_cases:
        console.print(f"[bold]📎 Similar Cases:[/bold] {', '.join(response.similar_cases)}")

    # ── Rule findings ───────────────────────────────────────────────────────
    if response.rule_findings:
        console.print(f"[bold]⚠️  Rule Findings:[/bold] ", end="")
        console.print(", ".join(f.rule for f in response.rule_findings))

    # ── Cache hit badge ──────────────────────────────────────────────────────
    if response.metadata.get("cache_hit"):
        console.print("[dim]⚡ Served from cache[/dim]")

    # ── Rewritten SQL ────────────────────────────────────────────────────────
    if show_rewrite and response.rewritten_sql:
        rw = response.rewritten_sql
        console.print(f"\n[bold cyan]🔁 REWRITTEN SQL[/bold cyan]")
        console.print(Panel(rw.rewritten, title="Corrected Query", border_style="cyan"))
        if rw.index_suggestions:
            console.print("[bold cyan]🔑 Index Suggestions:[/bold cyan]")
            for idx in rw.index_suggestions:
                console.print(f"   [cyan]{idx}[/cyan]")
        console.print(f"   Estimated improvement: [green]{rw.estimated_improvement}[/green]")
        console.print(f"   Safe to apply: {'[green]Yes[/green]' if rw.safe_to_apply else '[red]No — review manually[/red]'}")

    # ── Anomaly info ─────────────────────────────────────────────────────────
    if response.anomaly_info and response.anomaly_info.anomalies_detected:
        a = response.anomaly_info
        console.print(f"\n[bold red]🚨 ANOMALY DETECTED[/bold red]")
        console.print(f"   Severity: [red]{a.severity}[/red]")
        console.print(f"   Anomaly indices: {a.anomaly_indices}")

    console.print()


def _record_feedback(response, query: str) -> str:
    """Prompt for feedback and record it."""
    try:
        from src.learning.feedback_loop import FeedbackLoop
        from src.config import settings
        fb_choice = Prompt.ask(
            "[dim]📝 Was this helpful?[/dim]",
            choices=["y", "n", "s"],
            default="s",
        )
        if fb_choice != "s":
            feedback = "positive" if fb_choice == "y" else "negative"
            from src.ab_testing.ab_engine import ABTestingEngine
            ab = ABTestingEngine()
            variant = ab.get_variant(query)
            fl = FeedbackLoop(
                feedback_log_path=settings.feedback_log_path,
                knowledge_base_path=settings.knowledge_base_path,
            )
            fl.record(
                query=query,
                case_id=response.similar_cases[0] if response.similar_cases else None,
                suggestion="; ".join(response.suggestion[:2]),
                feedback=feedback,
                ab_variant=variant,
            )
            console.print(f"[dim]  Recorded: {feedback} (variant {variant})[/dim]")
        return fb_choice
    except Exception:
        return "s"


def _run_query(user_query: str, sql: str | None, show_rewrite: bool = False):
    """Run a single query through the orchestrator and render."""
    from src.agent.factory import create_orchestrator

    with console.status("[bold green]Analyzing...[/bold green]"):
        try:
            orch = create_orchestrator()
            response = orch.process(user_query, sql=sql)
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            return

    _render_response(response, user_query, show_rewrite=show_rewrite)
    return response


@click.command()
@click.argument("query", required=False)
@click.option("--sql", "-s", default=None, help="Explicit SQL to analyze")
@click.option("--rewrite", "-r", is_flag=True, help="Show rewritten SQL after response")
@click.option("--demo", is_flag=True, help="Run all 10 demo cases")
@click.option("--process-feedback", is_flag=True, help="Process feedback log and update vector store")
@click.option("--feedback-stats", is_flag=True, help="Show feedback statistics")
@click.option("--ab-results", is_flag=True, help="Show A/B testing results")
def cli(query, sql, rewrite, demo, process_feedback, feedback_stats, ab_results):
    """🧠 Query Intelligence Engine — Insurance PAS Performance Analyzer"""

    if demo:
        _run_demo()
        return

    if process_feedback:
        _process_feedback_cmd()
        return

    if feedback_stats:
        _feedback_stats_cmd()
        return

    if ab_results:
        _ab_results_cmd()
        return

    if query:
        console.print()
        console.rule("[bold blue]🧠 Query Intelligence Engine[/bold blue]")
        resp = _run_query(query, sql, show_rewrite=rewrite)
        if resp:
            _record_feedback(resp, query)
        return

    if not query:
        _interactive_mode()


def _interactive_mode():
    """REPL interactive mode."""
    console.print()
    console.print(Panel(
        "[bold blue]🧠 Query Intelligence Engine[/bold blue]\n"
        "[dim]Insurance PAS Performance Analyzer[/dim]\n\n"
        "Commands: [green]rewrite[/green] | [green]chain[/green] | [green]demo[/green] | [green]quit[/green]",
        border_style="blue",
    ))

    from src.agent.factory import create_orchestrator
    orch = create_orchestrator()
    last_response = None

    while True:
        try:
            user_input = Prompt.ask("\n[bold blue]>[/bold blue]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input.strip():
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye![/dim]")
            break
        if user_input.lower() == "demo":
            _run_demo()
            continue
        if user_input.lower() == "rewrite" and last_response:
            _render_response(last_response, "", show_rewrite=True)
            continue
        if user_input.lower() == "chain" and last_response:
            console.print_json(json.dumps(last_response.explanation_chain, indent=2))
            continue

        with console.status("[green]Analyzing...[/green]"):
            try:
                last_response = orch.process(user_input)
            except Exception as exc:
                console.print(f"[red]Error: {exc}[/red]")
                continue

        _render_response(last_response, user_input)
        _record_feedback(last_response, user_input)


def _run_demo():
    """Run all 10 demo cases."""
    console.print()
    console.rule("[bold yellow]🎬 DEMO — All 10 Cases[/bold yellow]")
    from src.agent.factory import create_orchestrator
    orch = create_orchestrator()

    for i, (q, sql) in enumerate(DEMO_QUERIES, 1):
        console.print(f"\n[bold cyan]── Case {i}/10 ──[/bold cyan]")
        console.print(f"[dim]Query:[/dim] {q}")
        if sql:
            console.print(f"[dim]SQL:[/dim]   {sql[:80]}{'...' if len(sql) > 80 else ''}")

        with console.status(f"[green]Analyzing case {i}...[/green]"):
            try:
                resp = orch.process(q, sql=sql)
            except Exception as exc:
                console.print(f"[red]Error: {exc}[/red]")
                continue

        _render_response(resp, q, show_rewrite=False)

    console.rule("[bold green]✅ Demo Complete[/bold green]")


def _process_feedback_cmd():
    from src.learning.feedback_loop import FeedbackLoop
    from src.config import settings
    console.print("[bold]Processing feedback log...[/bold]")
    fl = FeedbackLoop(settings.feedback_log_path, settings.knowledge_base_path)
    result = fl.process()
    console.print(f"✅ Updated: {result['updated']}")
    console.print(f"⚠️  Flagged: {result['flagged']}")
    console.print(f"📊 Processed: {result['processed']} entries")


def _feedback_stats_cmd():
    from src.learning.feedback_loop import FeedbackLoop
    from src.config import settings
    fl = FeedbackLoop(settings.feedback_log_path, settings.knowledge_base_path)
    stats = fl.get_stats()
    t = Table(title="Feedback Statistics", box=box.ROUNDED)
    t.add_column("Metric"); t.add_column("Value", style="green")
    t.add_row("Total responses", str(stats["total"]))
    t.add_row("Positive rate", f"{stats['positive_rate']*100:.1f}%")
    t.add_row("Cases flagged", str(stats["cases_flagged"]))
    console.print(t)


def _ab_results_cmd():
    from src.learning.feedback_loop import FeedbackLoop
    from src.ab_testing.ab_engine import ABTestingEngine
    from src.config import settings
    import json as _json
    fl = FeedbackLoop(settings.feedback_log_path, settings.knowledge_base_path)
    log = fl._load_log()
    ab = ABTestingEngine()
    results = ab.get_results(log)
    console.print_json(_json.dumps(results, indent=2))


if __name__ == "__main__":
    cli()
