"""规则过滤树（FilterTree）编译到 ES DSL。

背景：前端 `useRules.js` 的 `buildStageParams` / `cleanFilterTree` 产出的是
``{logic, filters}`` 对象，后端 `execute_*` 却用 ``for f in filters`` 迭代它 ——
拿到的是 dict 的 key 字符串，``f.get("field")`` 直接
``AttributeError: 'str' object has no attribute 'get'``。带逻辑组的规则每次执行都炸。
"""
from app.services.es_service import ESConfig, ESService


def _svc():
    return ESService(ESConfig(
        host="localhost", port=9200, scheme="http",
        verify_certs=False, user="", password="", default_index="security-logs-*",
    ))


def _leaf(field, operator, value):
    return {"field": field, "operator": operator, "value": value}


# ── 回归：旧格式必须原样可用 ──────────────────────────────────

def test_legacy_list_of_leaves_still_works():
    clause = _svc()._build_filters_clause([
        _leaf("status", "equals", 500),
        _leaf("src_ip", "equals", "1.2.3.4"),
    ])
    assert clause == {"bool": {"must": [
        {"term": {"status": 500}},
        {"term": {"src_ip": "1.2.3.4"}},
    ]}}


def test_legacy_single_leaf_is_bare():
    clause = _svc()._build_filters_clause([_leaf("status", "equals", 500)])
    assert clause == {"term": {"status": 500}}


# ── 回归：FilterTree 不再炸 ────────────────────────────────────

def test_filter_tree_dict_does_not_crash():
    """这是线上「规则都执行失败」的直接原因。"""
    tree = {"logic": "and", "filters": [
        _leaf("status", "equals", 500),
        {"logic": "or", "filters": [
            _leaf("path", "contains", "/admin"),
            _leaf("path", "contains", "/wp-login"),
        ]},
    ]}
    clause = _svc()._build_filters_clause(tree)
    assert clause == {"bool": {"must": [
        {"term": {"status": 500}},
        {"bool": {"should": [
            {"wildcard": {"path": "* /admin*".replace(" ", "")}},
            {"wildcard": {"path": "* /wp-login*".replace(" ", "")}},
        ], "minimum_should_match": 1}},
    ]}}


def test_or_group_at_root():
    tree = {"logic": "or", "filters": [
        _leaf("a", "equals", 1),
        _leaf("b", "equals", 2),
    ]}
    assert _svc()._build_filters_clause(tree) == {
        "bool": {"should": [{"term": {"a": 1}}, {"term": {"b": 2}}], "minimum_should_match": 1}
    }


def test_not_group_negates_conjunction():
    tree = {"logic": "not", "filters": [
        _leaf("a", "equals", 1),
        _leaf("b", "equals", 2),
    ]}
    assert _svc()._build_filters_clause(tree) == {
        "bool": {"must_not": [{"bool": {"must": [{"term": {"a": 1}}, {"term": {"b": 2}}]}}]}
    }


def test_not_wrapping_negative_operator_is_single_negation():
    """NOT (status != 500) 应当等价于 status == 500 的否定之否定，只包一层 must_not。"""
    tree = {"logic": "not", "filters": [_leaf("status", "not_equals", 500)]}
    clause = _svc()._build_filters_clause(tree)
    # 外层 not 一层 must_not，内层 not_equals 自带一层 —— 语义正确，不是双重否定成匹配。
    assert clause == {"bool": {"must_not": [{"bool": {"must_not": [{"term": {"status": 500}}]}}]}}


def test_empty_tree_is_none_not_crash():
    assert _svc()._build_filters_clause({"logic": "and", "filters": []}) is None
    assert _svc()._build_filters_clause({"logic": "and", "filters": [
        {"field": "", "operator": "equals", "value": 1}
    ]}) is None


def test_mixed_list_with_nested_tree():
    """旧列表里也能夹带嵌套组。"""
    payload = [
        _leaf("env", "equals", "prod"),
        {"logic": "or", "filters": [_leaf("x", "equals", 1), _leaf("y", "equals", 2)]},
    ]
    assert _svc()._build_filters_clause(payload) == {"bool": {"must": [
        {"term": {"env": "prod"}},
        {"bool": {"should": [{"term": {"x": 1}}, {"term": {"y": 2}}], "minimum_should_match": 1}},
    ]}}


def test_non_dict_entries_are_ignored():
    """以前这里会抛 AttributeError；现在必须安静跳过。"""
    assert _svc()._build_filters_clause(["logic", "filters", None, 123]) is None
