from __future__ import annotations

import json
import re

from src.models import RewriteResult
from src.analyzer.sql_parser import extract_table_names, extract_json_path
from src.rewriter.index_suggester import suggest_indexes


class QueryRewriter:
    """Rule-based SQL query rewriter.

    Applies a sequence of deterministic transformations to improve
    query performance.  Always shows what changed and why.
    Never executes SQL — text analysis only.
    """

    def __init__(self, schemas_path: str = "data/schemas.json") -> None:
        with open(schemas_path) as f:
            self.schemas: dict = json.load(f)

    # ─── Public API ──────────────────────────────────────────────────────────

    def rewrite(self, sql: str) -> RewriteResult:
        """Apply all rewrite rules to *sql* and return a RewriteResult."""
        if not sql or not sql.strip():
            return RewriteResult(
                original=sql or "",
                rewritten=sql or "",
                changes=[],
                index_suggestions=[],
                estimated_improvement="none",
                safe_to_apply=True,
            )

        sql = sql.strip()
        rewritten = sql
        changes: list[str] = []

        # ── Safety gate: UPDATE/DELETE without WHERE ──────────────────────────
        is_dml = bool(re.search(r"\b(UPDATE|DELETE)\b", sql, re.IGNORECASE))
        has_where = bool(re.search(r"\bWHERE\b", sql, re.IGNORECASE))
        if is_dml and not has_where:
            return RewriteResult(
                original=sql,
                rewritten=sql,
                changes=["⚠️  WARNING: UPDATE/DELETE without WHERE clause — NOT safe to auto-rewrite. Add WHERE clause manually."],
                index_suggestions=[],
                estimated_improvement="none",
                safe_to_apply=False,
            )

        tables = extract_table_names(sql)
        table = tables[0].lower() if tables else None
        schema = self.schemas.get(table, {}) if table else {}

        # ── Rule 1: SELECT * → specific columns ──────────────────────────────
        if re.search(r"SELECT\s+\*", rewritten, re.IGNORECASE):
            key_cols = schema.get("key_columns", [])
            if key_cols:
                col_str = ",\n       ".join(key_cols)
                rewritten = re.sub(
                    r"SELECT\s+\*",
                    f"SELECT {col_str}",
                    rewritten,
                    count=1,
                    flags=re.IGNORECASE,
                )
                changes.append(
                    f"Replaced SELECT * with specific columns: {', '.join(key_cols)}"
                )

        # ── Rule 2: No WHERE → inject safe filter ────────────────────────────
        is_select = bool(re.search(r"\bSELECT\b", rewritten, re.IGNORECASE))
        has_where_now = bool(re.search(r"\bWHERE\b", rewritten, re.IGNORECASE))
        if is_select and not has_where_now:
            safe_filter = schema.get("safe_filter")
            if safe_filter:
                rewritten = rewritten.rstrip(";").rstrip() + f"\nWHERE  {safe_filter}"
                changes.append(f"Added safe WHERE clause: {safe_filter}")

        # ── Rule 3: No LIMIT (SELECT without aggregate) ───────────────────────
        is_aggregate = bool(
            re.search(r"\b(COUNT|SUM|AVG|MAX|MIN)\s*\(", rewritten, re.IGNORECASE)
        )
        has_limit = bool(re.search(r"\bLIMIT\b", rewritten, re.IGNORECASE))
        if is_select and not has_limit and not is_aggregate:
            rewritten = rewritten.rstrip(";").rstrip() + "\nLIMIT  100\nOFFSET 0;"
            changes.append("Added LIMIT 100 OFFSET 0 for safe pagination")
        elif not rewritten.rstrip().endswith(";"):
            rewritten = rewritten.rstrip() + ";"

        # ── Rule 4: JSON_EXTRACT — add advisory comment ───────────────────────
        if re.search(r"JSON_EXTRACT", rewritten, re.IGNORECASE):
            json_path = extract_json_path(sql)
            if json_path:
                col_name = json_path.lstrip("$.").replace(".", "_")
                comment = (
                    f"-- NOTE: JSON_EXTRACT prevents index usage.\n"
                    f"-- Add generated column '{col_name}_gen' and index it (see index_suggestions).\n"
                )
                rewritten = comment + rewritten
                changes.append(
                    "Added guidance: JSON_EXTRACT requires a generated column + index for performance"
                )

        # ── Rule 5: Nested subquery → JOIN hint ───────────────────────────────
        if re.search(r"WHERE[\s\S]*\(\s*SELECT", sql, re.IGNORECASE) and len(changes) == 0:
            changes.append(
                "Consider rewriting the nested subquery as a JOIN or CTE for better optimization"
            )

        index_suggestions = suggest_indexes(sql, self.schemas)

        return RewriteResult(
            original=sql,
            rewritten=rewritten,
            changes=changes,
            index_suggestions=index_suggestions,
            estimated_improvement=self._estimate_improvement(changes),
            safe_to_apply=True,
        )

    # ─── Private Helpers ──────────────────────────────────────────────────────

    def _estimate_improvement(self, changes: list[str]) -> str:
        change_text = " ".join(changes).lower()
        if "where" in change_text or "select *" in change_text:
            return "~95-99% faster (eliminates full table scan)"
        if "limit" in change_text:
            return "moderate (limits result set size)"
        if "json" in change_text:
            return "significant (eliminates per-row JSON parsing after index added)"
        if "join" in change_text or "subquery" in change_text:
            return "moderate to significant (depends on index availability)"
        return "minor"
