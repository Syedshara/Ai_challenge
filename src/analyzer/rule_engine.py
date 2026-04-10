from __future__ import annotations
import json
import re
from pathlib import Path

from src.models import Finding


class QueryRuleEngine:
    """Deterministic SQL anti-pattern detector. Works 100% offline."""

    def __init__(self, patterns_path: str = "data/query_patterns.json"):
        with open(patterns_path) as f:
            self._patterns = json.load(f)["patterns"]

    # ─── Public API ──────────────────────────────────────────────────────────

    def analyze(self, sql: str) -> list[Finding]:
        """Run all rules against *sql* and return a list of Finding objects."""
        if not sql or not sql.strip():
            return []

        findings: list[Finding] = []
        sql_upper = sql.upper()

        # AP001: SELECT *
        if re.search(r"SELECT\s+\*", sql, re.IGNORECASE):
            findings.append(Finding(
                rule="SELECT_STAR",
                severity="warning",
                message="SELECT * fetches all columns including large JSON fields. Select only needed columns to reduce I/O.",
                fix="Replace SELECT * with an explicit column list: SELECT col1, col2, col3",
            ))

        # AP002: No WHERE clause (SELECT only — UPDATE checked separately)
        is_select = bool(re.search(r"\bSELECT\b", sql, re.IGNORECASE))
        has_where = bool(re.search(r"\bWHERE\b", sql, re.IGNORECASE))
        if is_select and not has_where:
            findings.append(Finding(
                rule="NO_WHERE_CLAUSE",
                severity="critical",
                message="No WHERE clause — query will perform a full table scan reading every row.",
                fix="Add a WHERE clause with an indexed column to filter rows",
            ))

        # AP003: JSON_EXTRACT in WHERE
        if re.search(r"JSON_EXTRACT", sql, re.IGNORECASE) and has_where:
            findings.append(Finding(
                rule="JSON_EXTRACT_IN_WHERE",
                severity="high",
                message="JSON_EXTRACT in WHERE clause cannot use standard B-tree indexes — full scan on every query.",
                fix="Add a generated column with the extracted value and create an index on it",
            ))

        # AP004: Nested subquery in WHERE
        if re.search(r"WHERE[\s\S]*\(\s*SELECT", sql, re.IGNORECASE):
            findings.append(Finding(
                rule="NESTED_SUBQUERY",
                severity="medium",
                message="Nested subquery in WHERE — may execute as a correlated subquery once per outer row.",
                fix="Rewrite as a JOIN or use a CTE (WITH clause) for better optimization",
            ))

        # AP005: No LIMIT for SELECT without aggregation
        is_aggregate = bool(re.search(r"\bCOUNT\s*\(|\bSUM\s*\(|\bAVG\s*\(|\bMAX\s*\(|\bMIN\s*\(", sql, re.IGNORECASE))
        has_limit = bool(re.search(r"\bLIMIT\b", sql, re.IGNORECASE))
        if is_select and not has_limit and not is_aggregate:
            findings.append(Finding(
                rule="NO_LIMIT",
                severity="warning",
                message="No LIMIT clause — query may return an unbounded result set consuming excessive memory.",
                fix="Add LIMIT 100 OFFSET 0 for safe pagination",
            ))

        # AP006: Multiple JOINs + JSON processing
        join_count = len(re.findall(r"\bJOIN\b", sql, re.IGNORECASE))
        if join_count >= 2 and re.search(r"\bJSON\b", sql, re.IGNORECASE):
            findings.append(Finding(
                rule="COMPLEX_JOIN_WITH_JSON",
                severity="high",
                message=f"{join_count} JOINs combined with JSON processing creates multiplicative I/O and parse cost.",
                fix="Materialize JSON fields into real columns; add composite indexes on join keys",
            ))

        # AP007: UPDATE without WHERE
        is_update = bool(re.search(r"\bUPDATE\b", sql, re.IGNORECASE))
        if is_update and not has_where:
            findings.append(Finding(
                rule="UPDATE_WITHOUT_WHERE",
                severity="critical",
                message="UPDATE without WHERE clause will modify ALL rows in the table!",
                fix="Add a WHERE clause to scope the UPDATE to only the intended rows",
            ))

        return findings

    def get_severity_score(self, findings: list[Finding]) -> float:
        """Aggregate severity as a 0.0–1.0 score."""
        weights = {"critical": 1.0, "high": 0.75, "medium": 0.5, "warning": 0.25, "info": 0.1}
        if not findings:
            return 0.0
        total = sum(weights.get(f.severity, 0.1) for f in findings)
        return round(min(total / (len(findings) * 1.0), 1.0), 3)
