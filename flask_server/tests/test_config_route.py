"""配置读写路由：分区块应用、校验与重启标记

为什么需要：
    配置接口是唯一能改服务端运行期行为的入口。改坏它要么让服务带着错配置重启，
    要么把非法值写进配置文件、下次启动直接失败。此前该路由零测试覆盖。

本文件覆盖：
    flask 区块   —— 只记录真正变化的项；host/port 改动触发重启标记
    tools 区块   —— 未声明工具被忽略；开关与语言列表即时生效
    limits 区块  —— 非整数、非正数被拒；合法值入库
    tool_config  —— 未声明的工具与键被忽略；类型转换失败被拒
    GET 快照     —— 字段齐全，URL 由 host/port 拼出
    POST 端到端  —— 变更列表与 requireRestart 标记符合预期

隔离策略：
    不调用 create_app（它会启动看门狗与后台线程），而是新建最小 Flask 实例、
    只注册被测蓝图；写配置与滚动重启替换为空实现，不触碰真实文件与进程。
    runtime.CONFIG 与 runtime.TOOLS 是进程级全局状态，统一在夹具里保存并还原。

运行：python -m pytest tests/test_config_route.py -q
"""
import copy

import pytest
from flask import Flask, request

import runtime
import tool_config
from routes import config_route


# 最小应用：只注册被测蓝图，并按项目惯例统一回应 OPTIONS 预检
_APP = Flask("config_route_test")
_APP.register_blueprint(config_route.bp)


@_APP.before_request
def _preflight():
    """OPTIONS 预检直接返回 204，避免每个用例各自处理。"""
    if request.method == "OPTIONS":
        return ("", 204)
    return None


@pytest.fixture(autouse=True)
def _restore_runtime():
    """保存并还原进程级全局状态，隔离用例。"""
    original_config = copy.deepcopy(runtime.CONFIG)
    original_tools = dict(runtime.TOOLS)
    yield
    runtime.CONFIG.clear()
    runtime.CONFIG.update(original_config)
    runtime.TOOLS.clear()
    runtime.TOOLS.update(original_tools)


@pytest.fixture
def app_ctx():
    """应用上下文：直接调用返回 jsonify 的内部函数时需要它。"""
    with _APP.app_context():
        yield


@pytest.fixture
def client(monkeypatch):
    """测试客户端：写配置与重启替换为空实现，避免副作用。"""
    monkeypatch.setattr(config_route, "save_config_to_yaml", lambda: True)
    monkeypatch.setattr(config_route, "rolling_restart", lambda port: None)
    return _APP.test_client()


class TestFlaskSection:
    """flask 区块：只记录变化项。"""

    def test_port_change_recorded(self):
        """端口变化写入配置并记入变更列表。"""
        runtime.CONFIG["flask"] = {"host": "127.0.0.1", "port": 5000}
        changed = []
        config_route._apply_flask_section({"flask": {"port": 5001}}, changed)
        assert changed == ["flask.port"]
        assert runtime.CONFIG["flask"]["port"] == 5001

    def test_same_value_not_recorded(self):
        """值未变化时不记入变更列表。"""
        runtime.CONFIG["flask"] = {"host": "127.0.0.1", "port": 5000}
        changed = []
        config_route._apply_flask_section({"flask": {"port": "5000"}}, changed)
        assert changed == []

    def test_non_dict_ignored(self):
        """flask 不是字典时整体忽略，不抛异常。"""
        changed = []
        config_route._apply_flask_section({"flask": "bad"}, changed)
        assert changed == []


class TestToolsSection:
    """tools 区块：上下线开关与语言列表。"""

    def test_undeclared_tool_ignored(self):
        """未注册的工具名不写入配置。"""
        runtime.TOOLS.clear()
        runtime.CONFIG["tools"] = {}
        changed = []
        config_route._apply_tools_section({"tools": {"ghost": {"enabled": False}}}, changed)
        assert changed == []
        assert "ghost" not in runtime.CONFIG["tools"]

    def test_enabled_flag_applied(self):
        """已注册工具的开关即时生效。"""
        runtime.TOOLS["read_file"] = {}
        runtime.CONFIG["tools"] = {}
        changed = []
        config_route._apply_tools_section({"tools": {"read_file": {"enabled": False}}}, changed)
        assert runtime.CONFIG["tools"]["read_file"]["enabled"] is False
        assert "tools.read_file=False" in changed

    def test_languages_normalized(self):
        """语言列表统一小写并去空白项。"""
        runtime.TOOLS["run_command"] = {}
        runtime.CONFIG["tools"] = {"run_command": {}}
        changed = []
        config_route._apply_tools_section(
            {"tools": {"run_command": {"enabled": True, "languages": [" PYTHON ", "", "Git"]}}},
            changed)
        assert runtime.CONFIG["tools"]["run_command"]["languages"] == ["python", "git"]


class TestLimitsSection:
    """limits 区块：体积上限必须是正整数。"""

    def test_non_integer_rejected(self, app_ctx):
        """非整数字符串被拒，返回 400 响应。"""
        resp = config_route._apply_limits_section(
            {"limits": {"max_json_chars": "abc"}}, [])
        assert resp is not None and resp[1] == 400

    def test_non_positive_rejected(self, app_ctx):
        """零和负数被拒。"""
        resp = config_route._apply_limits_section({"limits": {"max_json_chars": 0}}, [])
        assert resp is not None and resp[1] == 400

    def test_valid_value_applied(self):
        """合法值写入配置并记入变更列表。"""
        runtime.CONFIG["limits"] = {"max_json_chars": 1000}
        changed = []
        assert config_route._apply_limits_section({"limits": {"max_json_chars": 2000}}, changed) is None
        assert runtime.CONFIG["limits"]["max_json_chars"] == 2000
        assert changed == ["limits.max_json_chars=2000"]

    def test_missing_key_is_noop(self):
        """没有该键时什么也不做。"""
        changed = []
        assert config_route._apply_limits_section({"limits": {}}, changed) is None
        assert changed == []


class TestToolConfigSection:
    """tool_config 区块：按声明转换，未声明项忽略。"""

    def test_undeclared_tool_ignored(self):
        """未在声明里的工具不写入。"""
        runtime.CONFIG.setdefault("tool_config", {})
        changed = []
        assert config_route._apply_tool_config_section(
            {"tool_config": {"ghost_tool": {"x": 1}}}, changed) is None
        assert changed == []

    def test_undeclared_key_ignored(self):
        """已声明工具下未声明的键被忽略。"""
        runtime.CONFIG["tool_config"] = {}
        changed = []
        assert config_route._apply_tool_config_section(
            {"tool_config": {"read_file": {"no_such_key": 1}}}, changed) is None
        assert changed == []

    def test_invalid_value_rejected(self, app_ctx):
        """声明类型转换失败时返回 400。"""
        spec = tool_config.CONFIG_SCHEMA["read_file"][0]
        runtime.CONFIG["tool_config"] = {}
        resp = config_route._apply_tool_config_section(
            {"tool_config": {"read_file": {spec["key"]: object()}}}, [])
        assert resp is not None and resp[1] == 400


class TestSnapshotAndEndpoint:
    """GET 快照与 POST 端到端。"""

    def test_snapshot_fields(self, monkeypatch):
        """快照字段齐全，URL 由 host 与 port 拼出。"""
        monkeypatch.setattr(runtime, "CONFIG", {
            "flask": {"host": "127.0.0.1", "port": 5000},
            "limits": {"max_json_chars": 1000},
            "default_profile": "glm",
            "site_profiles": {},
            "tools": {},
        })
        monkeypatch.setattr(runtime, "TOOLS", {})
        snap = config_route._config_snapshot()
        assert snap["flask"]["url"] == "http://127.0.0.1:5000"
        assert snap["available_tools"] == []
        assert "tool_config" in snap and "system_config" in snap

    def test_post_port_change_requires_restart(self, client):
        """改端口时返回 requireRestart 为真。"""
        runtime.CONFIG["flask"] = {"host": "127.0.0.1", "port": 5000}
        resp = client.post("/config", json={"flask": {"port": 5001}})
        body = resp.get_json()
        assert resp.status_code == 200
        assert body["requireRestart"] is True
        assert "flask.port" in body["changed"]

    def test_post_without_flask_change_no_restart(self, client):
        """只改限制值时不要求重启。"""
        runtime.CONFIG["flask"] = {"host": "127.0.0.1", "port": 5000}
        runtime.CONFIG["limits"] = {"max_json_chars": 1000}
        resp = client.post("/config", json={"limits": {"max_json_chars": 2000}})
        body = resp.get_json()
        assert body["requireRestart"] is False
        assert body["changed"] == ["limits.max_json_chars=2000"]

    def test_get_returns_snapshot(self, client):
        """GET 返回完整快照。"""
        resp = client.get("/config")
        body = resp.get_json()
        assert resp.status_code == 200
        assert "flask" in body and "available_tools" in body

    def test_restart_port_rejects_non_integer(self, client):
        """端口不是整数时返回 400。"""
        resp = client.post("/config/restart-port", json={"port": "abc"})
        assert resp.status_code == 400

    def test_restart_port_rejects_out_of_range(self, client):
        """端口超出 1-65535 时返回 400。"""
        resp = client.post("/config/restart-port", json={"port": 70000})
        assert resp.status_code == 400

    def test_restart_port_ok(self, client):
        """合法端口返回成功并回显端口。"""
        resp = client.post("/config/restart-port", json={"port": 5001})
        body = resp.get_json()
        assert resp.status_code == 200
        assert body["success"] is True and body["port"] == 5001
