"""原始日志查询：否定子句不双重取反、响应带 ES took、显示上限夹紧。"""
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


# ── 显示上限 ────────────────────────────────────────────────────────────────
# 每页 50 条照旧，但最多只翻看 1000 条；命中数照实报，不受这个上限影响。

def test_default_page_size_is_50():
    """每页 50 条翻着看 —— 1000 条一页既卡表格也没必要。"""
    from app.api.raw_logs import DEFAULT_PAGE_SIZE, RawLogQuery

    assert DEFAULT_PAGE_SIZE == 50
    assert RawLogQuery().page_size == 50
    assert RawLogQuery().page == 1


def test_clamp_window_first_page():
    from app.api.raw_logs import _clamp_window

    assert _clamp_window(1, 50) == (50, 0)
    assert _clamp_window(1, 1) == (1, 0)
    assert _clamp_window(1, 1000) == (1000, 0), "一页最多 1000 条"


def test_clamp_window_caps_page_size():
    from app.api.raw_logs import MAX_PAGE_SIZE, _clamp_window

    size, from_ = _clamp_window(1, 100000)
    assert size == MAX_PAGE_SIZE and from_ == 0


def test_clamp_window_stops_at_max_display():
    """最多显示 1000 条：第 20 页是最后一页（50/页），第 21 页起点已在界外。"""
    from app.api.raw_logs import _clamp_window

    assert _clamp_window(20, 50) == (50, 950)
    assert _clamp_window(21, 50) == (None, None)


def test_clamp_window_shrinks_last_page():
    """末页只剩半页就缩 size，别让 from+size 越过显示上限。"""
    from app.api.raw_logs import _clamp_window

    # page=2, size=600 → from=600，只剩 400 的余量
    assert _clamp_window(2, 600) == (400, 600)


def test_clamp_window_tolerates_bad_input():
    from app.api.raw_logs import _clamp_window

    assert _clamp_window(0, 50) == (50, 0), "非法页码按第 1 页处理"
    assert _clamp_window(1, 0) == (50, 0), "非法条数回落到默认值"
    assert _clamp_window(-3, -3) == (50, 0)


class _FakeES:
    """只记录 search 收到的 body，不连 ES。"""

    last_body = None
    raise_on_search = False

    def __init__(self, config=None):
        self.client = self

    def _build_time_filter(self, window):
        return [{"range": {"@timestamp": {"gte": "now-1h"}}}]

    def search(self, index=None, body=None):
        if _FakeES.raise_on_search:
            raise AssertionError("显示上限外不该真的去查 ES")
        _FakeES.last_body = body
        return {
            "took": 12,
            "hits": {
                "total": {"value": 2500},
                "hits": [{"_source": {"src_ip": f"1.2.3.{i}"}} for i in range(body["size"])],
            },
        }


def test_query_keeps_50_per_page_and_reports_real_total(client, admin_user, monkeypatch):
    """每页 50 条，但 total 回 ES 的真实命中数 —— 显示上限不该把命中数也砍了。"""
    import app.api.raw_logs as rl
    from tests.conftest import login_headers

    _FakeES.last_body = None
    _FakeES.raise_on_search = False
    monkeypatch.setattr(rl, "ESService", _FakeES)
    h = login_headers(client)

    resp = client.post("/api/raw-logs/query", json={"dsl": "*:*"}, headers=h)
    body = resp.json()
    assert body["code"] == 200, body
    assert _FakeES.last_body["size"] == 50, "默认每页 50 条"
    assert _FakeES.last_body["from"] == 0
    data = body["data"]
    assert data["page_size"] == 50
    assert data["total"] == 2500, "命中数不变，照实报 ES 的总数"
    assert len(data["records"]) == 50
    assert data["max_display"] == 1000


def test_query_rejects_page_beyond_max_display_with_plain_message(client, admin_user, monkeypatch):
    """最多翻到第 20 页（50/页）。翻过头要给中文提示，不是 ES 的报错。"""
    import app.api.raw_logs as rl
    from tests.conftest import login_headers

    _FakeES.raise_on_search = True
    try:
        monkeypatch.setattr(rl, "ESService", _FakeES)
        h = login_headers(client)
        resp = client.post("/api/raw-logs/query", json={"dsl": "*:*", "page": 21, "page_size": 50}, headers=h)
        body = resp.json()
    finally:
        _FakeES.raise_on_search = False

    assert body["code"] == 400
    assert "最多显示前 1000 条" in body["msg"]


def test_query_clamps_last_page_size(client, admin_user, monkeypatch):
    """末页被夹小之后要按实际条数回，前端才好对齐分页器。"""
    import app.api.raw_logs as rl
    from tests.conftest import login_headers

    _FakeES.raise_on_search = False
    monkeypatch.setattr(rl, "ESService", _FakeES)
    h = login_headers(client)

    resp = client.post("/api/raw-logs/query", json={"dsl": "*:*", "page": 2, "page_size": 600}, headers=h)
    body = resp.json()
    assert body["code"] == 200, body
    assert _FakeES.last_body["size"] == 400
    assert _FakeES.last_body["from"] == 600
    assert body["data"]["page_size"] == 400
    assert body["data"]["page"] == 2
