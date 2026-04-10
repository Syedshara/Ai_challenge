#!/usr/bin/env python3
"""Live monitor demo launcher.

Usage:
    python demo_live.py           # Split-screen TUI (default)
    python demo_live.py --no-tui  # Plain Rich console output

First run (Docker not yet started):
    docker compose up -d          # starts MySQL, imports 4.1M rows (~5-10 min first time)
    python demo_live.py
"""
from __future__ import annotations

import os
import sys
import time

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ── MySQL wait helper ─────────────────────────────────────────────────────────

def _wait_for_mysql(host: str, port: int, user: str, password: str,
                    database: str, timeout: int = 600) -> bool:
    """
    Wait up to *timeout* seconds for MySQL to be ready.

    The 'reading initial communication packet' error is NORMAL during the
    first 5-10 minutes — MySQL is still running its init scripts (downloading
    and importing 4.1M rows). The loop will keep retrying every 5 seconds.
    It is not an error you need to act on; just wait.
    """
    try:
        import mysql.connector
    except ImportError:
        print("  ✗  mysql-connector-python not installed — run: pip install -r requirements.txt")
        return False

    INTERVAL  = 5
    elapsed   = 0
    last_err  = ""
    # Track the phase so we can give a useful message
    _INIT_ERRORS = (
        "reading initial communication packet",
        "Can't connect",
        "Connection refused",
    )

    while elapsed < timeout:
        try:
            cnx = mysql.connector.connect(
                host=host, port=port,
                user=user, password=password,
                database=database,
                connection_timeout=5,
                use_pure=True,          # avoid C-extension handshake issues
            )
            cur = cnx.cursor()
            cur.execute("SELECT COUNT(*) FROM employees")
            count = int(cur.fetchone()[0])
            cur.close()
            cnx.close()
            if count > 0:
                print(f"\n  ✓  MySQL ready — {count:,} employee rows loaded")
                return True
            last_err = "table empty (import still running)"
        except Exception as exc:
            last_err = str(exc)[:70]

        mins = elapsed // 60
        secs = elapsed % 60

        # Give a helpful message the first time we see the init error
        if elapsed == 0 and any(e in last_err for e in _INIT_ERRORS):
            print("      (This is normal — MySQL is still importing data.)")
            print("      The wait can take 5-10 minutes on first run.")

        sys.stdout.write(
            f"\r  ›  Waiting... {mins}m{secs:02d}s  {last_err[:65]:<65}"
        )
        sys.stdout.flush()
        time.sleep(INTERVAL)
        elapsed += INTERVAL

    print(f"\n  ✗  MySQL not ready after {timeout//60} min. Last error: {last_err}")
    print("     Check logs: docker compose logs mysql")
    return False


# ── TUI mode ──────────────────────────────────────────────────────────────────

def run_tui(orchestrator=None) -> None:
    from cli.live_monitor import LiveMonitorApp
    LiveMonitorApp(orchestrator=orchestrator).run()


# ── Console mode (--no-tui) ───────────────────────────────────────────────────

def run_console(orchestrator=None) -> None:
    """Rich console output — shows all 14 AI steps per slow query."""
    from rich.console import Console
    from rich.rule import Rule
    from rich.text import Text
    from rich.panel import Panel

    console = Console()

    from src.config import settings
    from src.monitor.models import MonitorConfig
    from src.monitor.connection import MonitoredConnection
    from src.pas.simulator import PASSimulator

    config = MonitorConfig.from_settings(settings)
    conn   = MonitoredConnection(config=config)
    if orchestrator is None:
        from src.agent.factory import create_orchestrator
        orchestrator = create_orchestrator()
    conn.set_orchestrator(orchestrator)

    # ── Step callback — prints each AI step as it fires ───────────────────
    SEV_STYLE = {
        "critical": "bold red", "high": "bold yellow",
        "medium": "yellow",     "low":  "green",
    }

    def on_step(step_type: str, *args) -> None:  # noqa: C901
        if step_type == "fast_query":
            ev = args[0]
            console.print(Text(
                f"  ✓  {ev.metrics.execution_time_ms:.1f}ms  fast — no analysis",
                style="dim green",
            ))
            return

        if step_type == "intercepted":
            ev = args[0]
            console.print(Text(
                f"\n  ⚡  INTERCEPTED  {ev.metrics.execution_time_ms:,.0f}ms  > threshold",
                style="bold red",
            ))
            return

        step_labels = {
            "cache":         "[01] Semantic Cache",
            "intent":        "[02] Intent Classification",
            "sql_extracted": "[03] SQL Extraction",
            "dense_search":  "[04] Dense Vector Search",
            "keyword_search":"[05] Keyword Search",
            "rrf_fusion":    "[06] RRF Fusion",
            "rerank":        "[07] Cross-Encoder Reranking",
            "rules":         "[08] Rule Engine",
            "ab_testing":    "[09] A/B Testing",
            "anomaly":       "[10] Anomaly Detection",
            "rewrite":       "[11] Query Rewriter",
            "confidence":    "[12] Confidence Score",
        }

        if step_type in step_labels:
            label = step_labels[step_type]
            data  = args[0] if args else None

            if step_type == "cache":
                val = "HIT — served from cache" if data else "MISS — fresh analysis"
                console.print(Text(f"  {label:<30} {val}", style="dim"))

            elif step_type == "intent":
                console.print(Text(f"  {label:<30} {data}", style="dim"))

            elif step_type == "sql_extracted":
                sql = str(data or "")[:65]
                console.print(Text(f"  {label:<30} {sql}", style="dim"))

            elif step_type == "dense_search":
                n = (data or {}).get("dense_count", "?")
                console.print(Text(f"  {label:<30} {n} candidates", style="dim"))

            elif step_type == "keyword_search":
                stats  = data or {}
                n      = stats.get("keyword_count", "?")
                tokens = stats.get("keywords_used", [])[:4]
                tok_s  = ", ".join(str(t) for t in tokens)
                console.print(Text(f"  {label:<30} {n} matches  [{tok_s}]", style="dim"))

            elif step_type == "rrf_fusion":
                stats = data or {}
                console.print(Text(
                    f"  {label:<30} dense({stats.get('dense_count','?')}) + "
                    f"keyword({stats.get('keyword_count','?')}) → {stats.get('merged_count','?')}",
                    style="dim",
                ))

            elif step_type == "rerank":
                cases = data or []
                console.print(Text(f"  {label:<30} top {len(cases)} selected", style="dim"))
                for i, c in enumerate(cases[:3], 1):
                    score = c.get("_rerank_score")
                    sc_s  = f"{score:.2f}" if score is not None else "n/a"
                    col   = "green" if score and score > 0 else "yellow" if score and score > -5 else "dim"
                    t = Text()
                    t.append(f"       {i}  {c.get('case_id','?'):<12}", style="dim")
                    t.append(f"  score:{sc_s:<7}", style=col)
                    t.append(c.get("title", "")[:40], style="dim")
                    console.print(t)

            elif step_type == "rules":
                findings = data or []
                console.print(Text(f"  {label:<30} {len(findings)} triggered", style="dim"))
                for f in findings:
                    sty = SEV_STYLE.get(f.severity, "white")
                    console.print(Text(
                        f"       ▶ {f.rule:<22} {f.severity}",
                        style=sty,
                    ))

            elif step_type == "ab_testing":
                variant = data or "?"
                lbl = "conservative" if variant == "A" else "aggressive"
                console.print(Text(f"  {label:<30} Variant {variant} ({lbl})", style="dim"))

            elif step_type == "anomaly":
                result = data
                if result is None:
                    console.print(Text(f"  {label:<30} not enough history", style="dim"))
                elif not result.anomalies_detected:
                    console.print(Text(f"  {label:<30} ✓ normal", style="dim green"))
                else:
                    console.print(Text(
                        f"  {label:<30} ▲ ANOMALY  {result.severity}",
                        style="bold red",
                    ))

            elif step_type == "rewrite":
                rw = data
                if rw and rw.changes:
                    console.print(Text(f"  {label:<30} {len(rw.changes)} change(s)", style="dim"))
                    for i, ch in enumerate(rw.changes, 1):
                        console.print(Text(f"       {i}  {ch[:70]}", style="dim"))
                else:
                    console.print(Text(f"  {label:<30} no changes", style="dim"))

            elif step_type == "confidence":
                bd = data or {}
                console.print(Text(
                    f"  {label:<30} {bd.get('total', 0):.2f}  "
                    f"(rule:{bd.get('rule',0):.2f} + rag:{bd.get('rag',0):.2f} + llm:{bd.get('llm',0):.2f})",
                    style="dim",
                ))

        elif step_type == "complete":
            result = args[0]
            sev    = result.severity.lower()
            style  = SEV_STYLE.get(sev, "white")
            conf   = int(result.confidence * 100)
            lines  = [
                f"[bold]{sev.upper()}[/bold]  ·  {conf}%  ·  {result.category}",
                "",
                result.problem,
                "",
            ]
            for i, s in enumerate(result.suggestion[:3], 1):
                lines.append(f"{i}. {s}")
            if result.rewritten_sql and result.rewritten_sql.changes:
                lines.append("")
                lines.append("[dim]Rewritten SQL:[/dim]")
                for ln in result.rewritten_sql.rewritten.splitlines()[:4]:
                    if ln.strip() and not ln.strip().startswith("--"):
                        lines.append(f"[blue]  {ln.rstrip()}[/blue]")
            console.print(Panel("\n".join(lines), border_style=style.replace("bold ", "")))

    conn.monitor.set_step_callback(on_step)

    # ── PAS callbacks ─────────────────────────────────────────────────────
    def on_start(op: dict) -> None:
        console.rule(
            f"[bold]Op {op['id']}/6  {op['name']}[/bold]",
            style="bright_black",
        )
        console.print(f"  [dim]{op['narrative']}[/dim]")
        console.print(f"  [blue]{' '.join(op['sql'].split())[:80]}[/blue]")
        console.print()

    def on_done(op: dict, event) -> None:
        if not event:
            console.print("  [red]✗ query failed[/red]"); return
        ms    = event.metrics.execution_time_ms
        rows  = event.metrics.rows_returned or 0
        style = "bold red" if event.is_slow else "green"
        console.print(Text(
            f"  {'SLOW ▲' if event.is_slow else 'fast ✓'}  {ms:,.0f}ms  rows:{rows:,}",
            style=style,
        ))
        if event.metrics.explain_output:
            ex  = event.metrics.explain_output[0]
            key = ex.key or "NONE"
            console.print(Text(
                f"  EXPLAIN  type={ex.type}  key={key}  est={ex.rows or '?'}",
                style="dim",
            ))
        console.print()

    sim = PASSimulator(conn=conn, on_start=on_start, on_done=on_done)

    console.print()
    console.rule("[bold orange1]Insurance PAS · Automated SQL Monitor[/bold orange1]")
    console.print(
        f"  Connected to [bold]{config.database}[/bold]"
        f"@{config.host}:{config.port}  "
        f"threshold:{config.slow_query_threshold_ms:.0f}ms\n"
    )

    try:
        sim.run_once()
        console.rule("[bold green]Demo complete[/bold green]")
        s = conn.monitor.get_summary()
        console.print(
            f"  Total:{s['total_queries']}  "
            f"Slow:{s['slow_queries']} ({s['slow_pct']:.0f}%)  "
            f"Avg:{s['avg_time_ms']:,.0f}ms"
        )
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    no_tui = "--no-tui" in sys.argv

    from src.config import settings

    print()
    print("  Insurance PAS · Live Monitor")
    print(f"  MySQL: {settings.mysql_host}:{settings.mysql_port}")
    print()

    ready = _wait_for_mysql(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        timeout=600,
    )

    if not ready:
        print()
        print("  ✗  Cannot connect to MySQL.")
        print("     If this is your first run, start the database with:")
        print("       docker compose up -d")
        print("     Then wait 5-10 minutes for the employees data to import.")
        print("     Once done, run this script again.")
        sys.exit(1)

    print("  Loading AI components (embeddings + vector store)...")
    from src.utils.silence import suppress_all
    suppress_all()
    from src.agent.factory import create_orchestrator
    orchestrator = create_orchestrator()
    print("  AI ready.\n")

    if no_tui:
        run_console(orchestrator=orchestrator)
    else:
        run_tui(orchestrator=orchestrator)
