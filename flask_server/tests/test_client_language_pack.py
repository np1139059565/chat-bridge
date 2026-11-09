r"""C-3a 语言包寄存通道测试：复用客户端注册的 custom_config 做原样寄存。

覆盖点：
  1. 含中文、嵌套、null、特殊字符的语言包存一遍取一遍深比较完全一致；
  2. 未注册 site_key 返回 404 与明确错误，不静默兜底到默认站点档案；
  3. 两个 site_key 互不串；重复注册整条覆盖；
  4. 服务端不解释字段，取回值与存入值按同一规则序列化后逐字节一致。

隔离策略：
    不调用 create_app，只注册 clients 蓝图；
    把 core/client_registry.py 的 REGISTRY_PATH 重定向到临时文件。

运行方式（在 .\flask_server\ 目录下）：
    python -m pytest tests/test_client_language_pack.py -q
"""
import json
import os
import sys
from pathlib import Path

import pytest
from flask import Flask

# 把服务根目录加入模块搜索路径，使扁平导入的被测模块可直接导入。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import client_registry as registry
from routes.clients import bp as clients_bp

# 语言包样例 A：翻译员私有数据，含中文、嵌套对象、数组、null、空串与特殊字符。
LANG_PACK_A = {
    "站点": "智谱清言",
    "选择器": {
        "输入框": "#search-input-box textarea, textarea.scroll-display-none",
        "发送按钮": 'div[role="button"].ds-button--primary',
        "容器": ".detail.chatScrollContainer.conversation-list",
        "生成态": ["aside.aside-container", ".is-main-chat.searching"],
    },
    "空值": None,
    "空串": "",
    "备注": "引号\" 单引号' 换行\n 制表\t 反斜杠\\ 中文😀 <>&",
    "嵌套": {"层级": {"三": [1, 2.5, True, None, "甲"]}},
}
# 语言包样例 B：结构完全不同，用于隔离与覆盖断言。
LANG_PACK_B = {
    "站点": "千问",
    "选择器": {"输入框": 'div[contenteditable="true"][role="textbox"]'},
    "仅此站点": ["甲"],
}


def _bytes_of(value):
    """按统一规则序列化为 UTF-8 字节串，用于逐字节一致实测。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


@pytest.fixture
def api(monkeypatch, tmp_path):
    """构造只注册客户端蓝图的最小应用，并隔离注册表落盘位置。"""
    monkeypatch.setattr(registry, "REGISTRY_PATH", tmp_path / "c3a_registry.json")
    app = Flask("c3a_language_pack_test")
    app.register_blueprint(clients_bp)

    @app.before_request
    def _shortcut():
        from flask import request
        # 预检请求直接短路，其余方法交给视图函数。
        if request.method == "OPTIONS":
            return ("", 204)

    return app.test_client()


def _post_pack(client, site_key, pack):
    """经 POST /api/clients 寄存一份语言包。"""
    return client.post("/api/clients", json={
        "site_key": site_key,
        "custom_config": pack,
        "commands": [],
    })


def _get_pack(client, site_key):
    """经 GET /api/clients 按 site_key 取回语言包。"""
    return client.get("/api/clients", query_string={"site_key": site_key})


def test_roundtrip_deep_equal(api):
    """寄存后取回：语言包深比较一致，且序列化后逐字节一致。"""
    r = _post_pack(api, "glm", LANG_PACK_A)
    assert r.status_code == 200
    assert r.get_json()["success"] is True
    body = _get_pack(api, "glm").get_json()
    assert body["success"] is True
    assert body["site_key"] == "glm"
    assert body["custom_config"] == LANG_PACK_A
    assert _bytes_of(body["custom_config"]) == _bytes_of(LANG_PACK_A)


def test_unregistered_not_fallback(api):
    """未注册 site_key：返回 404 与明确错误，不返回默认站点档案。"""
    r = _get_pack(api, "never-registered")
    assert r.status_code == 404
    body = r.get_json()
    assert body["success"] is False
    assert "未注册" in body["error"]
    # 不静默兜底：错误响应里不携带任何语言包或档案内容。
    assert "custom_config" not in body
    assert "profiles" not in body


def test_site_keys_isolated(api):
    """两个 site_key 的语言包互不串。"""
    _post_pack(api, "glm", LANG_PACK_A)
    _post_pack(api, "qianwen", LANG_PACK_B)
    a = _get_pack(api, "glm").get_json()["custom_config"]
    b = _get_pack(api, "qianwen").get_json()["custom_config"]
    assert a == LANG_PACK_A
    assert b == LANG_PACK_B
    assert a != b


def test_duplicate_register_overrides(api):
    """同一 site_key 重复注册：后者整条覆盖前者，不追加。"""
    _post_pack(api, "glm", LANG_PACK_A)
    r = _post_pack(api, "glm", LANG_PACK_B)
    assert r.status_code == 200
    body = _get_pack(api, "glm").get_json()
    assert body["custom_config"] == LANG_PACK_B
    assert "仅此站点" in body["custom_config"]


def test_server_does_not_interpret_fields(api):
    """服务端不解释字段：与档案同名的键也原样寄存、原样返回。"""
    pack = {"profiles": {"glm": {"inputSelector": "#x"}}, "site_profiles": None}
    _post_pack(api, "glm", pack)
    body = _get_pack(api, "glm").get_json()
    assert body["custom_config"] == pack
