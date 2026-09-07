"""自定义工具模块 custom_tools.py 的单元测试。"""
import json
import os
from pathlib import Path

import pytest

import custom_tools as ct


class TestParseSkill:
    def test_parse_valid_skill(self, skill_with_echo):
        skill_dir, _ = skill_with_echo
        parsed = ct.parse_skill(skill_dir)
        assert len(parsed) == 1
        tool = parsed[0]
        assert tool["name"] == "demo_echo"
        assert tool["description"] == "回声测试工具 # 含井号"
        assert tool["parameters"][0]["name"] == "msg"
        assert tool["parameters"][0]["required"] is True

    def test_parse_skill_missing_tool_json_raises(self, tmp_skill_dir):
        with pytest.raises(FileNotFoundError):
            ct.parse_skill(tmp_skill_dir)

    def test_parse_skill_invalid_json_raises(self, tmp_skill_dir):
        (tmp_skill_dir / "tool.json").write_text("{invalid", encoding="utf-8")
        with pytest.raises(ValueError):
            ct.parse_skill(tmp_skill_dir)

    def test_parse_skill_missing_name_raises(self, tmp_skill_dir):
        (tmp_skill_dir / "tool.json").write_text(
            json.dumps({"tools": [{"description": "no name", "script": "x.py"}]}),
            encoding="utf-8")
        with pytest.raises(ValueError):
            ct.parse_skill(tmp_skill_dir)

    def test_parse_skill_missing_description_raises(self, tmp_skill_dir):
        (tmp_skill_dir / "tool.json").write_text(
            json.dumps({"tools": [{"name": "valid_name", "script": "x.py"}]}),
            encoding="utf-8")
        with pytest.raises(ValueError):
            ct.parse_skill(tmp_skill_dir)

    def test_parse_skill_missing_script_raises(self, tmp_skill_dir):
        (tmp_skill_dir / "tool.json").write_text(
            json.dumps({"tools": [{"name": "valid_name", "description": "desc"}]}),
            encoding="utf-8")
        with pytest.raises(ValueError):
            ct.parse_skill(tmp_skill_dir)

    def test_parse_skill_nonexistent_script_raises(self, tmp_skill_dir):
        (tmp_skill_dir / "tool.json").write_text(
            json.dumps({"tools": [{"name": "n", "description": "d", "script": "missing.py"}]}),
            encoding="utf-8")
        with pytest.raises(FileNotFoundError):
            ct.parse_skill(tmp_skill_dir)

    def test_parse_skill_invalid_tool_name_raises(self, tmp_skill_dir):
        (tmp_skill_dir / "scripts" / "x.py").write_text("print(1)", encoding="utf-8")
        (tmp_skill_dir / "tool.json").write_text(
            json.dumps({"tools": [{"name": "bad-name!", "description": "d", "script": "scripts/x.py"}]}),
            encoding="utf-8")
        with pytest.raises(ValueError):
            ct.parse_skill(tmp_skill_dir)


class TestInstallRemoveUpdate:
    def test_install_success(self, skill_with_echo):
        skill_dir, _ = skill_with_echo
        installed = ct.install(skill_dir)
        assert installed == ["demo_echo"]
        assert ct.get_tool("demo_echo") is not None

    def test_install_conflict_with_builtin_raises(self, tmp_skill_dir):
        (tmp_skill_dir / "scripts" / "x.py").write_text("print(1)", encoding="utf-8")
        (tmp_skill_dir / "tool.json").write_text(
            json.dumps({"tools": [{"name": "list_dir", "description": "d", "script": "scripts/x.py"}]}),
            encoding="utf-8")
        with pytest.raises(ValueError):
            ct.install(tmp_skill_dir)

    def test_remove_nonexistent(self):
        assert ct.remove("nonexistent") is False

    def test_update_enabled(self, skill_with_echo):
        skill_dir, _ = skill_with_echo
        ct.install(skill_dir)
        updated = ct.update("demo_echo", {"enabled": True})
        assert updated["enabled"] is True
        assert ct.is_enabled("demo_echo") is True

    def test_update_nonexistent_returns_none(self):
        assert ct.update("nonexistent", {"enabled": True}) is None


class TestRun:
    def test_run_echo_success(self, skill_with_echo):
        skill_dir, _ = skill_with_echo
        ct.install(skill_dir)
        tool = ct.get_tool("demo_echo")
        result = ct.run(tool, {"msg": "你好", "repeat": True})
        assert result == {"msg": "你好你好", "repeat": True}

    def test_run_missing_required_param_raises(self, skill_with_echo):
        skill_dir, _ = skill_with_echo
        ct.install(skill_dir)
        tool = ct.get_tool("demo_echo")
        with pytest.raises(ValueError):
            ct.run(tool, {})

    def test_run_script_error_raises(self, tmp_skill_dir):
        (tmp_skill_dir / "scripts" / "fail.py").write_text(
            "import sys\nsys.exit(1)\n", encoding="utf-8")
        (tmp_skill_dir / "tool.json").write_text(
            json.dumps({"tools": [{"name": "failing_tool", "description": "d", "script": "scripts/fail.py"}]}),
            encoding="utf-8")
        ct.install(tmp_skill_dir)
        tool = ct.get_tool("failing_tool")
        with pytest.raises(RuntimeError):
            ct.run(tool, {})

    def test_run_plain_stdout_wrapped(self, tmp_skill_dir):
        (tmp_skill_dir / "scripts" / "plain.py").write_text(
            "print('hello world')\n", encoding="utf-8")
        (tmp_skill_dir / "tool.json").write_text(
            json.dumps({"tools": [{"name": "plain_tool", "description": "d", "script": "scripts/plain.py"}]}),
            encoding="utf-8")
        ct.install(tmp_skill_dir)
        tool = ct.get_tool("plain_tool")
        result = ct.run(tool, {})
        assert result == {"stdout": "hello world"}


class TestYamlRoundTrip:
    def test_save_and_load_preserves_fields(self, skill_with_echo):
        skill_dir, _ = skill_with_echo
        ct.install(skill_dir)
        loaded = ct.load_tools()
        assert "demo_echo" in loaded
        assert loaded["demo_echo"]["description"] == "回声测试工具 # 含井号"
        assert loaded["demo_echo"]["enabled"] is False
        # 保存后重新加载
        assert ct.save_tools(loaded) is True
        loaded_again = ct.load_tools()
        assert loaded_again["demo_echo"]["description"] == "回声测试工具 # 含井号"


class TestScanDir:
    def test_scan_dir_finds_skill(self, skill_with_echo, tmp_path):
        skill_dir, _ = skill_with_echo
        scanned = ct.scan_dir(tmp_path)
        assert any(s["skill_name"] == skill_dir.name for s in scanned)

    def test_scan_dir_nonexistent_raises(self):
        with pytest.raises(ValueError):
            ct.scan_dir("nonexistent_dir_xyz")
