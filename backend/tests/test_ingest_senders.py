"""远程接收：token 可选 + 接收端认人 + 手动绑定。

远程端脚本已经写死不能改，所以身份只能由接收端从第一包特征里认，管理员
手动绑定起名字。绑定是标注不是闸门 —— 日报勾了哪个接口就取它最近一条数据，
跟 token 和绑定都无关。
"""
import json

from tests.conftest import login_headers


def _make_endpoint(client, h, name="daily"):
    resp = client.post("/api/remote/endpoints", json={"name": name}, headers=h)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _push(name, payload='{"cpu":1}', headers=None, client=None):
    h = {"content-type": "application/json"}
    if headers:
        h.update(headers)
    return client.post(f"/api/remote/ingest/{name}", content=payload, headers=h)


def test_ingest_without_token_is_accepted(client):
    """远程端脚本不带 token —— 必须收。"""
    h = login_headers(client)
    _make_endpoint(client, h, "no-token")
    resp = _push("no-token", '{"cpu":1}', client=client)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["sender_status"] == "pending"


def test_wrong_token_still_rejected_when_provided(client):
    """带了 token 就必须对 —— 用上了就不能默默放行错误密钥。"""
    h = login_headers(client)
    ep = _make_endpoint(client, h, "locked")
    assert ep.get("token")
    resp = _push("locked", '{"cpu":1}', headers={"X-Ingest-Token": "wrong"}, client=client)
    assert resp.status_code == 401
    resp = _push("locked", '{"cpu":1}', headers={"X-Ingest-Token": ep["token"]}, client=client)
    assert resp.status_code == 200


def test_first_send_creates_pending_sender_with_features(client):
    h = login_headers(client)
    _make_endpoint(client, h, "feat")
    _push("feat", '{"cpu":1,"mem":2}', headers={"User-Agent": "agent/1.0"}, client=client)

    listed = client.get("/api/remote/senders", headers=h)
    assert listed.status_code == 200
    items = listed.json()["data"]["items"]
    assert len(items) == 1
    s = items[0]
    assert s["status"] == "pending"
    assert s["user_agent"] == "agent/1.0"
    assert s["payload_shape"] == "cpu,mem"
    assert s["send_count"] == 1
    assert "cpu" in s["sample_payload"]


def test_same_features_group_into_one_sender(client):
    h = login_headers(client)
    _make_endpoint(client, h, "group")
    for _ in range(3):
        _push("group", '{"cpu":1}', headers={"User-Agent": "agent/1.0"}, client=client)
    items = client.get("/api/remote/senders", headers=h).json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["send_count"] == 3


def test_different_shape_is_a_different_sender(client):
    h = login_headers(client)
    _make_endpoint(client, h, "shapes")
    _push("shapes", '{"cpu":1}', headers={"User-Agent": "agent/1.0"}, client=client)
    _push("shapes", '{"disk":1}', headers={"User-Agent": "agent/1.0"}, client=client)
    items = client.get("/api/remote/senders", headers=h).json()["data"]["items"]
    assert len(items) == 2


def test_selected_endpoint_reports_latest_data_regardless_of_bind(client):
    """勾了接口就要那条数据 —— 不看 token，也不看绑定状态。"""
    h = login_headers(client)
    _make_endpoint(client, h, "report")
    _push("report", '{"cpu":42}', client=client)
    _push("report", '{"cpu":99}', client=client)  # 更新的一条
    ep_id = client.get("/api/remote/endpoints", headers=h).json()["data"][0]["id"]

    # 还没绑定：勾了就要
    before = client.get(
        "/api/reports/inspection",
        params={"endpoint_ids": str(ep_id), "script_ids": "", "include_monitoring": "false"},
        headers=h,
    )
    assert before.status_code == 200, before.text
    rows = before.json()["data"]["ingested"]
    assert len(rows) == 1
    assert "cpu" in rows[0]["payload"]

    # 绑定只是给发送方起名字，不改变「要不要」
    sender_id = client.get("/api/remote/senders", headers=h).json()["data"]["items"][0]["id"]
    client.post(
        f"/api/remote/senders/{sender_id}/bind",
        json={"display_name": "web-01"},
        headers=h,
    )
    after = client.get(
        "/api/reports/inspection",
        params={"endpoint_ids": str(ep_id), "script_ids": "", "include_monitoring": "false"},
        headers=h,
    )
    rows = after.json()["data"]["ingested"]
    assert len(rows) == 1
    assert rows[0]["sender_name"] == "web-01"
    assert "cpu" in rows[0]["payload"]


def test_unselected_endpoint_stays_out_of_report(client):
    """没勾的接口不进日报 —— 勾选才是唯一的闸门。"""
    h = login_headers(client)
    _make_endpoint(client, h, "checked")
    _make_endpoint(client, h, "unchecked")
    _push("checked", '{"a":1}', client=client)
    _push("unchecked", '{"b":2}', client=client)
    eps = client.get("/api/remote/endpoints", headers=h).json()["data"]
    checked_id = next(e["id"] for e in eps if e["name"] == "checked")

    resp = client.get(
        "/api/reports/inspection",
        params={"endpoint_ids": str(checked_id), "script_ids": "", "include_monitoring": "false"},
        headers=h,
    )
    rows = resp.json()["data"]["ingested"]
    assert len(rows) == 1
    assert rows[0]["endpoint_name"] == "checked"


def test_bind_needs_ops_power_not_view(client, operator_user, viewer_user):
    """认人是写报告的人的日常活儿（operate），不是授权（manage_authz）。

    旧注释把「绑定」说成铸身份的授权行为，那是在拿绑定当日报闸门的思路 ——
    闸门早就改回接口勾选了，绑定只是给发送方起个名字。
    """
    h_op = login_headers(client, "operator", "OperPass1")
    h_v = login_headers(client, "viewer", "ViewPass1")
    h = login_headers(client)
    _make_endpoint(client, h, "rbac")
    _push("rbac", '{"a":1}', client=client)
    sender_id = client.get("/api/remote/senders", headers=h).json()["data"]["items"][0]["id"]

    # 读：任意登录角色
    assert client.get("/api/remote/senders", headers=h_op).status_code == 200
    assert client.get("/api/remote/senders", headers=h_v).status_code == 200

    # 只读用户不能绑
    resp = client.post(f"/api/remote/senders/{sender_id}/bind", json={"display_name": "x"}, headers=h_v)
    assert resp.status_code == 403

    # 业务操作员可以绑
    resp = client.post(f"/api/remote/senders/{sender_id}/bind", json={"display_name": "x"}, headers=h_op)
    assert resp.status_code == 200
