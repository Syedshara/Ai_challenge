"""Tests for the QueryRewriter and IndexSuggester."""
import re
import pytest


def test_rewrites_select_star_to_columns(rewriter):
    result = rewriter.rewrite("SELECT * FROM policy_data")
    assert not re.search(r"SELECT\s+\*", result.rewritten, re.IGNORECASE)
    assert result.safe_to_apply is True
    assert len(result.changes) >= 1


def test_adds_where_clause_when_missing(rewriter):
    result = rewriter.rewrite("SELECT * FROM policy_data")
    assert "WHERE" in result.rewritten


def test_adds_limit_when_missing(rewriter):
    result = rewriter.rewrite("SELECT * FROM policy_data")
    assert "LIMIT" in result.rewritten


def test_does_not_rewrite_unsafe_update(rewriter):
    sql = "UPDATE policy_data SET status = 'EXPIRED'"
    result = rewriter.rewrite(sql)
    assert result.safe_to_apply is False
    assert result.rewritten == sql


def test_handles_json_extract(rewriter):
    sql = "SELECT * FROM policy_data WHERE JSON_EXTRACT(data, '$.policy.state') = 'CA'"
    result = rewriter.rewrite(sql)
    assert len(result.changes) > 0
    assert len(result.index_suggestions) > 0


def test_generates_create_index_statement(rewriter):
    result = rewriter.rewrite("SELECT * FROM policy_data")
    index_stmts = " ".join(result.index_suggestions).upper()
    assert "CREATE INDEX" in index_stmts


def test_no_crash_on_empty_input(rewriter):
    result = rewriter.rewrite("")
    assert result is not None
    assert result.original == ""


def test_no_crash_on_none_style_empty(rewriter):
    result = rewriter.rewrite("   ")
    assert result is not None


def test_rewrite_result_has_all_fields(rewriter):
    from src.models import RewriteResult
    result = rewriter.rewrite("SELECT * FROM policy_data")
    assert isinstance(result, RewriteResult)
    assert isinstance(result.changes, list)
    assert isinstance(result.index_suggestions, list)
    assert isinstance(result.estimated_improvement, str)


def test_update_with_where_is_safe(rewriter):
    sql = "UPDATE policy_data SET status = 'EXPIRED' WHERE created_date < '2020-01-01'"
    result = rewriter.rewrite(sql)
    assert result.safe_to_apply is True
