"""Flask API 路由测试：/tools、/tool、/config、/hot_fix、自定义工具路由。"""
import json
import os

import pytest


class TestToolsList:
    def test_get_tools_returns_all_enabled_by_default(self, app):
        resp = app.get("/tools")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["tools"]
        names = {t["name"] for t in data["tools"]}
        assert "list_dir" in names
        assert "read_file" in names
        # 自愈工具始终在线
        assert "hot_reload_fix" in names


class TestToolCall:
    def test_call_list_dir_success(self, app, tmp_path):
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        resp = app.post("/tool", json={
            "tool": "list_dir",
            "parameters": {"target_directory": str(tmp_path)},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert any(item["name"] == "a.txt" for item in data["result"]["items"])

    def test_call_tool_missing_parameter_returns_parameter_origin(self, app):
        resp = app.post("/tool", json={
            "tool": "list_dir",
            "parameters": {},
        })
        data = resp.get_json()
        assert data["success"] is False
        assert data["origin"] == "parameter"

    def test_call_tool_wrong_alias_returns_parameter_origin(self, app):
        resp = app.post("/tool", json={
            "tool": "list_dir",
            "parameters": {"path": "flask_server"},
        })
        data = resp.get_json()
        assert data["success"] is False
        assert data["origin"] == "parameter"

    def test_call_unknown_tool_returns_404(self, app):
        resp = app.post("/tool", json={
            "tool": "nonexistent_tool",
            "parameters": {},
        })
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["origin"] == "unknown_tool"

    def test_call_disabled_tool_returns_disabled_origin(self, app):
        # 先下线 list_dir
        resp = app.post("/config", json={
            "tools": {"list_dir": {"enabled": False}},
        })
        assert resp.get_json()["success"] is True
        # 再调用
        resp = app.post("/tool", json={
            "tool": "list_dir",
            "parameters": {"target_directory": "flask_server"},
        })
        data = resp.get_json()
        assert data["success"] is False
        assert data["origin"] == "disabled"


class TestConfig:
    def test_get_config_returns_defaults(self, app):
        resp = app.get("/config")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "flask" in data
        assert "port" in data["flask"]
        assert "tools" in data

    def test_post_config_port_change_requires_restart(self, app):
        resp = app.post("/config", json={"flask": {"port": 8080}})
        data = resp.get_json()
        assert data["success"] is True
        assert data["requireRestart"] is True

    def test_post_config_tool_toggle_no_restart(self, app):
        resp = app.post("/config", json={
            "tools": {"read_file": {"enabled": False}},
        })
        data = resp.get_json()
        assert data["success"] is True
        assert data["requireRestart"] is False

    def test_post_config_same_port_no_change(self, app):
        current_port = app.get("/config").get_json()["flask"]["port"]
        resp = app.post("/config", json={"flask": {"port": current_port}})
        data = resp.get_json()
        assert data["changed"] == []
        assert data["requireRestart"] is False


class TestCustomToolsRoutes:
    def test_get_custom_tools_empty(self, app):
        resp = app.get("/custom_tools")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["tools"] == []

    def test_scan_empty_dir(self, app, tmp_path):
        resp = app.post("/custom_tools/scan", json={"dir": str(tmp_path)})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["skills"] == []

    def test_install_and_manage_custom_tool(self, app, skill_with_echo):
        skill_dir, _ = skill_with_echo
        # 安装
        resp = app.post("/custom_tools/install", json={"dir": str(skill_dir)})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["installed"] == ["demo_echo"]

        # 列表应包含新工具
        resp = app.get("/custom_tools")
        names = {t["name"] for t in resp.get_json()["tools"]}
        assert "demo_echo" in names

        # 启用并更新
        resp = app.put("/custom_tools/demo_echo", json={"enabled": True})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

        # 删除
        resp = app.delete("/custom_tools/demo_echo")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True


class TestHotFix:
    def test_hot_fix_missing_params_returns_parameter_origin(self, app):
        resp = app.post("/hot_fix", json={})
        data = resp.get_json()
        assert data["success"] is False
        assert data["origin"] == "parameter"
