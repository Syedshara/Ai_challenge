"""Tests for the SQL rule engine and parser."""
import pytest
import re


def test_detects_select_star(rule_engine):
    findings = rule_engine.analyze("SELECT * FROM policy_data")
    rules = [f.rule for f in findings]
    assert "SELECT_STAR" in rules


def test_detects_no_where_clause(rule_engine):
    findings = rule_engine.analyze("SELECT * FROM policy_data")
    rules = [f.rule for f in findings]
    assert "NO_WHERE_CLAUSE" in rules


def test_detects_json_extract_in_where(rule_engine):
    sql = "SELECT * FROM policy_data WHERE JSON_EXTRACT(data, '$.state') = 'CA'"
    findings = rule_engine.analyze(sql)
    rules = [f.rule for f in findings]
    assert "JSON_EXTRACT_IN_WHERE" in rules


def test_detects_nested_subquery(rule_engine):
    sql = "SELECT * FROM claims_data WHERE policy_id IN (SELECT policy_id FROM policy_data WHERE state = 'CA')"
    findings = rule_engine.analyze(sql)
    rules = [f.rule for f in findings]
    assert "NESTED_SUBQUERY" in rules


def test_detects_no_limit(rule_engine):
    sql = "SELECT policy_id FROM policy_data WHERE status = 'ACTIVE'"
    findings = rule_engine.analyze(sql)
    rules = [f.rule for f in findings]
    assert "NO_LIMIT" in rules


def test_detects_update_without_where(rule_engine):
    findings = rule_engine.analyze("UPDATE policy_data SET status = 'EXPIRED'")
    rules = [f.rule for f in findings]
    assert "UPDATE_WITHOUT_WHERE" in rules


def test_no_false_positive_on_good_query(rule_engine):
    sql = "SELECT policy_id, status FROM policy_data WHERE status = 'ACTIVE' LIMIT 100"
    findings = rule_engine.analyze(sql)
    critical = [f for f in findings if f.severity == "critical"]
    assert len(critical) == 0, f"Unexpected critical findings: {[f.rule for f in critical]}"


def test_empty_sql_returns_no_findings(rule_engine):
    assert rule_engine.analyze("") == []
    assert rule_engine.analyze(None) == []


def test_fingerprint_removes_literals():
    from src.analyzer.sql_parser import fingerprint
    sql = "SELECT * FROM policy_data WHERE state = 'CA' AND premium > 1200"
    fp = fingerprint(sql)
    assert "CA" not in fp
    assert "1200" not in fp
    assert "POLICY_DATA" in fp


def test_fingerprint_normalizes_whitespace():
    from src.analyzer.sql_parser import fingerprint
    sql = "SELECT  *  FROM  policy_data"
    fp = fingerprint(sql)
    assert "  " not in fp


def test_extract_sql_from_text():
    from src.analyzer.sql_parser import extract_sql
    text = "Why is SELECT * FROM policy_data slow?"
    sql = extract_sql(text)
    assert sql is not None
    assert "SELECT" in sql.upper()


def test_classify_intent_query_analysis():
    from src.analyzer.intent import classify_intent
    assert classify_intent("Why is this query slow?") == "query_analysis"


def test_classify_intent_optimization():
    from src.analyzer.intent import classify_intent
    assert classify_intent("How can I optimize this SQL?") == "optimization"


def test_classify_intent_anomaly():
    from src.analyzer.intent import classify_intent
    assert classify_intent("Is this a latency spike anomaly?") == "anomaly_detection"


def test_classify_intent_system_design():
    from src.analyzer.intent import classify_intent
    assert classify_intent("What would you change in the system design?") == "system_design"
