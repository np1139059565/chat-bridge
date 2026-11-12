"""B-5 / 桥接指令三接口测试：commands CRUD、help、run-command。

覆盖点：
  1. /api/bridge/commands：新增 / 修改 / 删除 / 回读；
     负路径含非斜杠名、内置冲突、重名、组合子指令不存在、下标越界
  2. /api/bridge/help：help 纯文本与 groups 结构化分组同回；
     自定义指令单独成组；空类不产生空组
  3. /api/bridge/run-command：非指令文本拒绝；内置 /help 可执行；
     自定义指令命中即 handled（无页面绑定时不下发，但仍算处理）

隔离策略：最小蓝图应用；配置双文件与内存缓存重定向到临时目录；
外部指令源清零，断言不依赖本机安装的 skill。

运行方式（在 .\\flask_server\\ 目录下）：
    python -m pytest tests/test_bridge_command_routes.py -q
"""
import os
import sys

import pytest
from flask import Flask, request as _req

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import config_file
import custom_tools.commands as ext_cmds
from remote_bridge import bridge_store as bs
from remote_bridge import command_groups as cg
from routes.bridge import bp as bridge_bp

# 合法的点击类自定义指令样例，各负路径在其副本上改字段。
ENTRY = {"name": "/mycmd", "label": "测试指令",
         "selector": "#btn", "page_url": "https://a.example"}


def _options_passthrough():
    """OPTIONS 预检短路为 204，其余方法进入视图。"""
    return ("", 204) if _req.method == "OPTIONS" else None


@pytest.fixture
def cmd_api(monkeypatch, tmp_path):
    """最小应用：挂桥接蓝图；配置与外部指令源全部隔离。"""
    monkeypatch.setattr(config_file, "DEFINITION_PATH", tmp_path / "definition.yaml")
    monkeypatch.setattr(config_file, "RUNTIME_PATH", tmp_path / "runtime.yaml")
    monkeypatch.setattr(bs, "_CONFIG", None)
    monkeypatch.setattr(ext_cmds, "list_external_commands", lambda: [])
    monkeypatch.setattr(ext_cmds, "external_command_names", lambda: set())
    monkeypatch.setattr(cg, "_external_commands", lambda: [])
    app = Flask("b5_bridge_test")
    app.register_blueprint(bridge_bp)
    app.before_request(_options_passthrough)
    yield app.test_client()


def _post_cmd(client, entry, index=None):
    """按接口格式提交一条指令（index 为 None 即新增）。"""
    return client.post("/api/bridge/commands",
                       json={"index": index, "entry": entry})


class TestCommandsCrud:
    """指令增删改查的接口契约。"""

    def test_get_initially_empty(self, cmd_api):
        """初始状态返回空指令列表。"""
        body = cmd_api.get("/api/bridge/commands").get_json()
        assert body["success"] is True
        assert body["commands"] == []

    def test_post_adds_and_persists(self, cmd_api, monkeypatch):
        """合法指令可新增；清缓存强制重读仍在（真落盘）。"""
        resp = _post_cmd(cmd_api, ENTRY)
        assert resp.get_json()["success"] is True
        monkeypatch.setattr(bs, "_CONFIG", None)
        listed = cmd_api.get("/api/bridge/commands").get_json()["commands"]
        assert listed and listed[0]["name"] == "/mycmd"

    def test_post_rejects_name_without_slash(self, cmd_api):
        """命令名必须以 / 开头。"""
        bad = dict(ENTRY, name="mycmd")
        body = _post_cmd(cmd_api, bad).get_json()
        assert body["success"] is False
        assert "开头" in body["error"]

    def test_post_rejects_builtin_conflict(self, cmd_api):
        """与内置指令（含别名）重名被拒。"""
        bad = dict(ENTRY, name="/help")
        body = _post_cmd(cmd_api, bad).get_json()
        assert body["success"] is False
        assert "内置指令冲突" in body["error"]

    def test_post_rejects_duplicate_custom(self, cmd_api):
        """与已有自定义指令重名被拒。"""
        _post_cmd(cmd_api, ENTRY)
        body = _post_cmd(cmd_api, ENTRY).get_json()
        assert body["success"] is False
        assert "已存在" in body["error"]

    def test_post_combo_rejects_missing_step(self, cmd_api):
        """组合指令引用不存在的子指令被拒。"""
        combo = {"name": "/combo", "label": "组合", "steps": ["/ghost-step"]}
        body = _post_cmd(cmd_api, combo).get_json()
        assert body["success"] is False
        assert "不存在" in body["error"]

    def test_post_update_replaces_entry(self, cmd_api):
        """带 index 的提交替换该下标指令。"""
        _post_cmd(cmd_api, ENTRY)
        newer = dict(ENTRY, label="改名")
        resp = _post_cmd(cmd_api, newer, index=0)
        assert resp.get_json()["success"] is True
        listed = cmd_api.get("/api/bridge/commands").get_json()["commands"]
        assert listed[0]["label"] == "改名"

    def test_post_out_of_range_index_fails(self, cmd_api):
        """修改时下标越界返回失败。"""
        body = _post_cmd(cmd_api, ENTRY, index=7).get_json()
        assert body["success"] is False
        assert "越界" in body["error"]

    def test_delete_removes_entry(self, cmd_api):
        """合法下标删除成功。"""
        _post_cmd(cmd_api, ENTRY)
        resp = cmd_api.delete("/api/bridge/commands", json={"index": 0})
        assert resp.get_json()["success"] is True
        assert cmd_api.get("/api/bridge/commands").get_json()["commands"] == []

    def test_delete_out_of_range_fails(self, cmd_api):
        """越界下标删除返回失败与错误文本。"""
        body = cmd_api.delete("/api/bridge/commands", json={"index": 9}).get_json()
        assert body["success"] is False
        assert "越界" in body["error"]


class TestBridgeHelp:
    """help 双数据的接口契约。"""

    def test_returns_text_and_groups(self, cmd_api):
        """同回 help 纯文本与 groups 结构化分组。"""
        body = cmd_api.get("/api/bridge/help").get_json()
        assert body["success"] is True
        assert body["help"].startswith("可用指令：")
        assert isinstance(body["groups"], list) and body["groups"]

    def test_groups_include_custom(self, cmd_api):
        """自定义指令单独成组，条目带 name 供前端渲染。"""
        _post_cmd(cmd_api, ENTRY)
        body = cmd_api.get("/api/bridge/help").get_json()
        cus = [g for g in body["groups"] if g["group"] == "自定义指令"]
        assert cus and cus[0]["items"][0]["name"] == "/mycmd"

    def test_no_empty_group_when_custom_absent(self, cmd_api):
        """自定义与外部均空时不产生空组。"""
        body = cmd_api.get("/api/bridge/help").get_json()
        names = [g["group"] for g in body["groups"]]
        assert "自定义指令" not in names
        assert "外部指令" not in names


class TestRunCommand:
    """run-command 执行入口的接口契约。"""

    def test_rejects_empty_text(self, cmd_api):
        """空文本不是指令。"""
        resp = cmd_api.post("/api/bridge/run-command", json={"text": ""})
        body = resp.get_json()
        assert body["success"] is False
        assert body["error"] == "not_a_command"

    def test_rejects_non_slash_text(self, cmd_api):
        """不以 / 开头的文本不当作指令。"""
        resp = cmd_api.post("/api/bridge/run-command", json={"text": "hello"})
        body = resp.get_json()
        assert body["success"] is False
        assert body["error"] == "not_a_command"

    def test_builtin_help_is_handled(self, cmd_api):
        """内置 /help 可执行：web-user 回执走出口，无 QQ 依赖。"""
        resp = cmd_api.post("/api/bridge/run-command", json={"text": "/help"})
        body = resp.get_json()
        assert body["success"] is True
        assert body["handled"] is True

    def test_custom_command_is_handled(self, cmd_api):
        """自定义指令命中即 handled：无绑定不下发，仍算处理。"""
        _post_cmd(cmd_api, ENTRY)
        resp = cmd_api.post("/api/bridge/run-command", json={"text": "/mycmd"})
        body = resp.get_json()
        assert body["success"] is True
        assert body["handled"] is True
