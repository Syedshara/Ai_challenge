from __future__ import annotations

from src.analyzer.sql_parser import (
    extract_table_names,
    extract_where_columns,
    extract_join_columns,
    extract_json_path,
)


def suggest_indexes(sql: str, schemas: dict) -> list[str]:
    """Generate specific ``CREATE INDEX`` SQL statements for *sql*.

    Inspects WHERE columns, JOIN columns, and JSON paths to produce
    actionable, copy-paste-ready index DDL.
    """
    suggestions: list[str] = []
    tables = extract_table_names(sql)
    if not tables:
        return suggestions
    table = tables[0].lower()
    schema = schemas.get(table, {})

    # Indexes for WHERE clause columns
    where_cols = extract_where_columns(sql)

    # If no WHERE columns found, suggest index on the safe_filter column
    if not where_cols and schema.get("safe_filter"):
        import re as _re
        m = _re.search(r'([a-zA-Z_]+)\s*=', schema["safe_filter"])
        if m:
            where_cols = [m.group(1).strip()]

    for col in where_cols:
        if col.lower() == "key":
            continue  # config_table.key is already UNIQUE indexed
        suggestions.append(
            f"CREATE INDEX idx_{table}_{col} ON {table}({col});"
        )

    # Indexes for JOIN ON columns
    join_cols = extract_join_columns(sql)
    for col in join_cols:
        if col not in where_cols:
            suggestions.append(
                f"CREATE INDEX idx_{table}_{col} ON {table}({col});"
            )

    # Composite index when multiple WHERE columns exist
    if len(where_cols) > 1:
        cols_str = ", ".join(where_cols)
        name_str = "_".join(where_cols)
        suggestions.append(
            f"CREATE INDEX idx_{table}_{name_str} ON {table}({cols_str});  -- composite"
        )

    # Generated column + index for JSON_EXTRACT
    json_path = extract_json_path(sql)
    if json_path:
        col_name = json_path.lstrip("$.").replace(".", "_")
        suggestions.append(
            f"-- Recommended: add a generated (virtual) column and index it\n"
            f"ALTER TABLE {table}\n"
            f"  ADD COLUMN {col_name}_gen VARCHAR(255)\n"
            f"  GENERATED ALWAYS AS\n"
            f"  (JSON_UNQUOTE(JSON_EXTRACT(data, '{json_path}'))) STORED;\n"
            f"CREATE INDEX idx_{table}_{col_name} ON {table}({col_name}_gen);"
        )

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique
