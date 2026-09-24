"""界面外观配置（UI 管理）。

外观只是展示层的旋钮，但它走的是 system_config 那条「未知 key 硬拒」的路 ——
种子没跑、迁移没跑的库会直接把界面管理页废掉。这里钉住 `_ensure_ui_config`
的兜底行为。
"""


def _login(client, u, p):
    from tests.conftest import login_headers

    return login_headers(client, u, p)


UI_KEYS = [
    "ui_theme",
    "ui_primary_color",
    "ui_density",
    "ui_sidebar_collapse",
    "ui_site_title",
]


def test_ui_keys_are_auto_created_on_read(client, admin_user):
    """SEED_SYSTEM_CONFIG=0 的库（就是测试库）也能读到 ui_* 项。"""
    h = _login(client, "admin", "AdminPass1")
    data = client.get("/api/settings/config", headers=h).json()["data"]
    flat = {item["key"] for arr in data.values() for item in arr}
    for k in UI_KEYS:
        assert k in flat, f"{k} 没被 _ensure_ui_config 补上"


def test_ui_config_can_be_saved(client, admin_user):
    h = _login(client, "admin", "AdminPass1")
    resp = client.put(
        "/api/settings/config",
        json={"updates": {
            "ui_theme": "dark",
            "ui_primary_color": "#67c23a",
            "ui_density": "small",
            "ui_sidebar_collapse": "true",
            "ui_site_title": "我的平台",
        }},
        headers=h,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 200

    data = client.get("/api/settings/config", headers=h).json()["data"]
    flat = {item["key"]: item["value"] for arr in data.values() for item in arr}
    assert flat["ui_theme"] == "dark"
    assert flat["ui_primary_color"] == "#67c23a"
    assert flat["ui_density"] == "small"
    assert flat["ui_sidebar_collapse"] == "true"
    assert flat["ui_site_title"] == "我的平台"


def test_unknown_keys_still_rejected(client, admin_user):
    """兜底只开给 ui_* —— 其余未知 key 照旧硬拒，免得又出现「保存成功但没生效」。"""
    h = _login(client, "admin", "AdminPass1")
    resp = client.put(
        "/api/settings/config",
        json={"updates": {"ui_whatever": "1", "not_a_real_key": "2"}},
        headers=h,
    )
    assert resp.json()["code"] == 400


def test_ui_config_needs_manage_system(client, operator_user, sec_admin_user):
    hop = _login(client, "operator", "OperPass1")
    assert client.put(
        "/api/settings/config", json={"updates": {"ui_theme": "dark"}}, headers=hop
    ).status_code == 403

    hs = _login(client, "sec", "SecPass1!")
    assert client.put(
        "/api/settings/config", json={"updates": {"ui_theme": "dark"}}, headers=hs
    ).status_code == 403

    # 读是开放的 —— 全站外观人人看得见
    assert client.get("/api/settings/config", headers=hop).status_code == 200
