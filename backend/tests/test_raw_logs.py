"""原始日志查询：否定子句不双重取反、响应带 ES took。"""
from types import SimpleNamespace


def test_all_not_equals_clause_is_already_negated():
    """_build_condition_clause 对 _all 取反自带 must_not，调用方不能再塞进 must_not。"""
    from app.api.raw_logs import _build_condition_clause, QueryCondition

    clause = _build_condition_clause(QueryCondition(field="_all", operator="not_equals", value="noise"))
    assert "bool" in clause and "must_not" in clause["bool"]


def test_negation_operators_return_must_not_form():
    from app.api.raw_logs import _build_condition_clause, QueryCondition

    for op in ("not_equals", "not_contains", "not_exists"):
        clause = _build_condition_clause(QueryCondition(field="src_ip", operator=op, value="1.2.3.4"))
        assert "bool" in clause and "must_not" in clause["bool"], op


def test_positive_operators_are_bare_clauses():
    from app.api.raw_logs import _build_condition_clause, QueryCondition

    assert "term" in _build_condition_clause(QueryCondition(field="src_ip", operator="equals", value="1.2.3.4"))
    assert "wildcard" in _build_condition_clause(QueryCondition(field="src_ip", operator="contains", value="1.2"))
    assert "exists" in _build_condition_clause(QueryCondition(field="src_ip", operator="exists"))
    assert "range" in _build_condition_clause(QueryCondition(field="request_status", operator="gte", value="400"))
