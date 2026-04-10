from __future__ import annotations
import re


# ─── SQL Extraction ──────────────────────────────────────────────────────────

_SQL_PATTERN = re.compile(
    r'\b(SELECT|UPDATE|INSERT|DELETE|WITH)\b[\s\S]+?(?=\s*$|[\n]{2,}|(?=[A-Z][a-z]))',
    re.IGNORECASE,
)

def extract_sql(text: str) -> str | None:
    """Extract a SQL statement from a natural language query string."""
    if not text:
        return None
    # If the text itself looks like SQL, return it directly
    if re.match(r'^\s*(SELECT|UPDATE|INSERT|DELETE|WITH)\b', text, re.IGNORECASE):
        return text.strip()
    # Look for SQL embedded in natural language
    match = re.search(r'(SELECT|UPDATE|INSERT|DELETE|WITH)\s+[\s\S]+', text, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    return None


# ─── SQL Fingerprinting ───────────────────────────────────────────────────────

def fingerprint(sql: str) -> str:
    """Normalize a SQL query for pattern comparison.

    Replaces literals with placeholders and uppercases keywords so
    'SELECT * FROM policy WHERE state = 'CA' AND premium > 1200'
    becomes 'SELECT * FROM POLICY WHERE STATE = '?' AND PREMIUM > ?'.
    """
    if not sql:
        return ""
    result = sql
    result = re.sub(r"'[^']*'", "'?'", result)        # string literals → '?'
    result = re.sub(r"\b\d+(\.\d+)?\b", "?", result)  # numbers → ?
    result = re.sub(r"\s+", " ", result)               # collapse whitespace
    return result.strip().upper()


# ─── Table Name Extraction ────────────────────────────────────────────────────

def extract_table_names(sql: str) -> list[str]:
    """Extract table names from FROM and JOIN clauses."""
    if not sql:
        return []
    tables: list[str] = []
    # FROM <table> and JOIN <table>
    for match in re.finditer(
        r'\b(?:FROM|JOIN)\s+([`"\[]?[\w]+[`"\]]?)(?:\s+(?:AS\s+)?[\w]+)?',
        sql,
        re.IGNORECASE,
    ):
        name = match.group(1).strip('`"[]')
        if name.upper() not in ("SELECT", "WHERE", "ON", "SET"):
            tables.append(name.lower())
    return list(dict.fromkeys(tables))  # deduplicate preserving order


# ─── WHERE Column Extraction ──────────────────────────────────────────────────

def extract_where_columns(sql: str) -> list[str]:
    """Extract column names referenced in the WHERE clause."""
    if not sql:
        return []
    where_match = re.search(r'\bWHERE\b([\s\S]+?)(?:\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|\bHAVING\b|$)',
                            sql, re.IGNORECASE)
    if not where_match:
        return []
    where_clause = where_match.group(1)
    # Match <table.>column = value patterns
    cols = re.findall(r'(?:[\w]+\.)?([a-zA-Z_][\w]*)(?:\s*[=<>!]|(?:\s+(?:IN|LIKE|BETWEEN|IS)\b))',
                      where_clause, re.IGNORECASE)
    # Filter out SQL keywords and operators
    keywords = {"AND", "OR", "NOT", "NULL", "TRUE", "FALSE", "IN", "LIKE", "BETWEEN", "IS",
                "SELECT", "FROM", "WHERE", "JOIN"}
    return [c.lower() for c in cols if c.upper() not in keywords and not c.isdigit()]


# ─── JOIN Column Extraction ───────────────────────────────────────────────────

def extract_join_columns(sql: str) -> list[str]:
    """Extract column names from JOIN … ON clauses."""
    if not sql:
        return []
    cols: list[str] = []
    for on_match in re.finditer(r'\bON\b([\s\S]+?)(?:\bWHERE\b|\bJOIN\b|\bGROUP BY\b|\bORDER BY\b|$)',
                                sql, re.IGNORECASE):
        on_clause = on_match.group(1)
        found = re.findall(r'(?:[\w]+\.)?([a-zA-Z_][\w]*)', on_clause, re.IGNORECASE)
        cols.extend(c.lower() for c in found if c.upper() not in ("AND", "OR", "ON"))
    return list(dict.fromkeys(cols))


# ─── JSON Path Extraction ─────────────────────────────────────────────────────

def extract_json_path(sql: str) -> str | None:
    """Extract the JSON path string from JSON_EXTRACT(col, '$.path') expressions."""
    if not sql:
        return None
    match = re.search(r"JSON_EXTRACT\s*\([^,]+,\s*'(\$[^']*)'\s*\)", sql, re.IGNORECASE)
    return match.group(1) if match else None
