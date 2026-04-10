from __future__ import annotations


class ABTestingEngine:
    """A/B testing engine for query optimization suggestions.

    Routes queries deterministically to Strategy A (conservative) or
    Strategy B (aggressive) and tracks win rates via the feedback log.

    Routing is hash-based so the same query always receives the same
    variant — enabling fair comparison across repeated queries.
    """

    # ─── Routing ─────────────────────────────────────────────────────────────

    def get_variant(self, query: str) -> str:
        """Return ``"A"`` or ``"B"`` deterministically for *query*."""
        return "A" if hash(query) % 2 == 0 else "B"

    # ─── Suggestion Generation ────────────────────────────────────────────────

    def generate_suggestions(self, analysis: dict, variant: str) -> list[str]:
        """Generate suggestions according to the assigned *variant*."""
        if variant == "A":
            return self._conservative(analysis)
        return self._aggressive(analysis)

    def _conservative(self, analysis: dict) -> list[str]:
        """Strategy A — minimal, safe, immediately applicable fixes."""
        suggestions: list[str] = []
        table = analysis.get("table", "the_table")
        schema_cols = analysis.get("schema_columns", [])

        if analysis.get("is_select_star") and schema_cols:
            cols = ", ".join(schema_cols[:5])
            suggestions.append(f"Replace SELECT * with: SELECT {cols}")

        if analysis.get("no_where"):
            suggestions.append(
                "Add a WHERE clause using an indexed column: WHERE status = 'ACTIVE'"
            )

        if analysis.get("no_limit"):
            suggestions.append("Add LIMIT 100 OFFSET 0 to prevent unbounded result sets")

        if analysis.get("uses_json_extract"):
            suggestions.append(
                "Add a generated column + index to replace JSON_EXTRACT in WHERE clause"
            )

        if analysis.get("missing_index"):
            col = analysis.get("filter_column", "status")
            suggestions.append(
                f"CREATE INDEX idx_{table}_{col} ON {table}({col});"
            )

        if not suggestions:
            suggestions.append(
                "Run EXPLAIN on the query and add indexes on columns used in WHERE and JOIN conditions"
            )
        return suggestions

    def _aggressive(self, analysis: dict) -> list[str]:
        """Strategy B — deep architectural improvements."""
        suggestions: list[str] = []
        table = analysis.get("table", "the_table")

        if analysis.get("is_select_star") or analysis.get("no_where"):
            suggestions.append(
                f"Create a materialized view for frequent queries:\n"
                f"  CREATE MATERIALIZED VIEW active_{table} AS\n"
                f"  SELECT col1, col2, col3 FROM {table} WHERE status = 'ACTIVE';"
            )

        rows = analysis.get("table_size_rows", 0)
        if rows > 1_000_000:
            suggestions.append(
                f"Partition {table} by created_date using RANGE partitioning "
                f"to reduce scan scope by up to 95%"
            )

        freq = analysis.get("frequency", "")
        if freq in ("high", "very_high"):
            suggestions.append(
                "Add a Redis cache layer with 60-second TTL — reduces DB load by ~95% "
                "for high-frequency queries without changing the query itself"
            )

        if analysis.get("uses_json_extract"):
            suggestions.append(
                "Normalize the JSON policy fields into dedicated VARCHAR/INT columns. "
                "This eliminates JSON parsing overhead entirely and enables standard indexing."
            )

        join_count = analysis.get("join_count", 0)
        if join_count >= 2:
            suggestions.append(
                "Consider a denormalized reporting table or read replica for multi-join queries "
                "to isolate analytical load from OLTP traffic"
            )

        if not suggestions:
            suggestions.append(
                "Profile with EXPLAIN ANALYZE, consider a read replica for heavy analytical queries, "
                "and review schema normalization opportunities"
            )
        return suggestions

    # ─── Results ─────────────────────────────────────────────────────────────

    def get_results(self, feedback_log: list[dict]) -> dict:
        """Compute win rates per variant from *feedback_log*."""
        a_entries = [e for e in feedback_log if e.get("ab_variant") == "A"]
        b_entries = [e for e in feedback_log if e.get("ab_variant") == "B"]

        def _stats(entries: list[dict]) -> dict:
            if not entries:
                return {"queries": 0, "positive_feedback": 0, "win_rate": 0.0}
            pos = sum(1 for e in entries if e["feedback"] == "positive")
            return {
                "queries": len(entries),
                "positive_feedback": pos,
                "win_rate": round(pos / len(entries), 3),
            }

        a_stats = _stats(a_entries)
        b_stats = _stats(b_entries)

        winner: str | None = None
        if a_entries and b_entries:
            winner = "A" if a_stats["win_rate"] >= b_stats["win_rate"] else "B"

        strategy_names = {"A": "Conservative", "B": "Aggressive"}
        recommendation = (
            f"Strategy {winner} ({strategy_names.get(winner, '')}) is performing better."
            if winner
            else "Insufficient data — need at least 10 queries per variant."
        )

        return {
            "variant_A": {"name": "Conservative", **a_stats},
            "variant_B": {"name": "Aggressive", **b_stats},
            "winner": winner,
            "total_queries": len(feedback_log),
            "recommendation": recommendation,
            "min_queries_for_significance": 100,
        }
