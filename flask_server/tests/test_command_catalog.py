r"""C-2 指令清单查询接口测试：覆盖三来源合并与帮助文本分组。

隔离策略：
    不调用 create_app（会启动看门狗与后台线程），只注册相关蓝图；
    把 core/client_registry.py 的 REGISTRY_PATH 重定向到临时文件；
    内置表与自定义来源用 monkeypatch 注入，不依赖本机真实配置。

运行方式（在 .\flask_server\ 目录下）：
    python -m pytest tests/test_command_catalog.py -q
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from flask import Flask

# 把服务根目录加入模块搜索路径，使扁平导入的被测模块可直接导入。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import client_registry as registry
import command_catalog as catalog
from routes.clients import bp as clients_bp
from routes.command_catalog import bp as catalog_bp

# 内置来源假数据：两条指令，覆盖有别名与无别名两种展示形态。
BUILTIN_FAKE = [
    {"name": "/side", "source": catalog.BUILTIN, "desc": "抽屉在左/右之间切换"},
    {"name": "/help", "source": catalog.BUILTIN, "desc": "显示指令列表"},
]
# 自定义来源假数据：与客户端来源同名，用于检验同名指令不去重。
CUSTOM_FAKE = [
    {"name": "/dbg-open", "source": catalog.CUSTOM, "desc": "外部调试"},
]
# 客户端声明：两个站点会注册同一条指令，验收时用 site_key 区分。
CLIENT_CMDS = [
    {"name": "/dbg-open", "alias": "/do", "desc": "打开调试抽屉", "tool": "open_drawer"},
]


def _options_shortcut():
    """OPTIONS 预检统一短路，其他方法继续进入视图函数。"""
    from flask import request
    # 只在预检时返回 204，避免改动任何业务响应。
    return ("", 204) if request.method == "OPTIONS" else None


@pytest.fixture
def api(monkeypatch):
    """构造只注册相关蓝图的最小应用，并隔离注册表落盘位置。"""
    work = tempfile.mkdtemp(prefix="c2_catalog_")
    # 每个用例一张空注册表，互不污染，也不触碰真实数据目录。
    monkeypatch.setattr(registry, "REGISTRY_PATH", Path(work) / "registry.json")
    # 内置与自定义来源替换为可控假数据，断言不依赖本机安装状态。
    monkeypatch.setattr(catalog, "_builtin_items", lambda: list(BUILTIN_FAKE))
    monkeypatch.setattr(catalog, "_custom_items", lambda: list(CUSTOM_FAKE))
    app = Flask("c2_catalog_test")
    # 注册接口用来写入客户端声明，清单接口是本次被测对象。
    app.register_blueprint(clients_bp)
    app.register_blueprint(catalog_bp)
    # 预检处理用模块级函数，避免与既有测试的嵌套写法形成连续重复块。
    app.before_request(_options_shortcut)
    yield app.test_client(), work
    # 用例结束清理临时目录；monkeypatch 由 pytest 自动还原。
    shutil.rmtree(work, ignore_errors=True)


def _register(client, key):
    """经客户端注册接口写入一个站点及其可执行指令声明。"""
    payload = {
        "site_key": key,
        "custom_config": {},
        "commands": CLIENT_CMDS,
    }
    # 复用 C-1 的注册接口，保证测试走真实落盘链路。
    return client.post("/api/clients", json=payload)


def _items(client):
    """取回统一指令清单，只保留 commands 数组便于断言。"""
    # 接口异常时直接抛断言错误，暴露真实状态码问题。
    resp = client.get("/api/commands")
    assert resp.status_code == 200
    return resp.get_json()["commands"]


def _by_source(entries):
    """按 source 把清单项分桶，便于逐来源核对。"""
    buckets = {}
    for row in entries:
        # 逐条归入对应来源，保留原始顺序。
        buckets.setdefault(row["source"], []).append(row)
    return buckets


def test_three_sources_merged(api):
    """查询全部指令：三个来源都在，每项含名称、来源、说明。"""
    client, _work = api
    assert _register(client, "glm").status_code == 200
    rows = _items(client)
    buckets = _by_source(rows)
    assert {r["name"] for r in buckets[catalog.BUILTIN]} >= {"/side", "/help"}
    assert {r["name"] for r in buckets[catalog.CUSTOM]} == {"/dbg-open"}
    assert {r["name"] for r in buckets[catalog.CLIENT]} == {"/dbg-open"}
    # 字段完整性：统一视图至少含这三个字段。
    assert all({"name", "source", "desc"}.issubset(r) for r in rows)


def test_no_client_registered(api):
    """无客户端注册：只返回内置与自定义来源，不报错。"""
    client, _work = api
    buckets = _by_source(_items(client))
    assert catalog.BUILTIN in buckets
    assert catalog.CUSTOM in buckets
    # 注册表为空时，客户端来源不应出现，也不应产生异常。
    assert catalog.CLIENT not in buckets


def test_client_registered_appears(api):
    """有客户端注册后：清单含该客户端声明的指令，来源标为 client。"""
    client, _work = api
    assert _register(client, "glm").status_code == 200
    client_rows = _by_source(_items(client))[catalog.CLIENT]
    assert len(client_rows) == 1
    assert client_rows[0]["name"] == "/dbg-open"
    # 归属字段让同名指令可追溯到具体站点。
    assert client_rows[0]["site_key"] == "glm"


def test_two_clients_same_command(api):
    """两个客户端声明同名指令：两条都出现，用 site_key 区分。"""
    client, _work = api
    assert _register(client, "glm").status_code == 200
    assert _register(client, "deepseek").status_code == 200
    rows = [r for r in _items(client)
            if r["source"] == catalog.CLIENT and r["name"] == "/dbg-open"]
    assert len(rows) == 2
    # 集合比较忽略顺序，只关心两个归属都保留。
    assert {r["site_key"] for r in rows} == {"glm", "deepseek"}


def test_help_text_grouped_and_consistent(api):
    """帮助文本按来源分组，内容与清单一致。"""
    client, _work = api
    assert _register(client, "glm").status_code == 200
    rows = _items(client)
    resp = client.get("/api/commands/help")
    assert resp.status_code == 200
    text = resp.get_json()["help"]
    assert "**内置指令**" in text
    assert "**自定义指令**" in text
    assert "**客户端指令**" in text
    # 清单里每条指令的名称与说明都应在帮助文本中出现。
    for row in rows:
        assert "`%s`" % row["name"] in text
        assert row["desc"] in text


def test_empty_builtin_table(api, monkeypatch):
    """内置指令表为空：不报错，返回其余来源。"""
    client, _work = api
    monkeypatch.setattr(catalog, "_builtin_items", lambda: [])
    buckets = _by_source(_items(client))
    assert catalog.BUILTIN not in buckets
    assert catalog.CUSTOM in buckets
    # 空来源不产生空分组，帮助文本仍可读。
    text = client.get("/api/commands/help").get_json()["help"]
    assert "**内置指令**" not in text
