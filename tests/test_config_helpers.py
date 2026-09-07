"""server.py 配置解析 / 保存辅助函数的补充测试。"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "flask_server"))

import server


class TestCoerce:
    def test_coerce_int(self):
        assert server._coerce("123") == 123

    def test_coerce_float(self):
        assert server._coerce("3.14") == 3.14

    def test_coerce_bool_true(self):
        assert server._coerce("true") is True

    def test_coerce_bool_false(self):
        assert server._coerce("false") is False

    def test_coerce_null(self):
        assert server._coerce("null") is None
        assert server._coerce("~") is None

    def test_coerce_quoted_string(self):
        assert server._coerce('"hello"') == "hello"
        assert server._coerce("'world'") == "world"

    def test_coerce_plain_string(self):
        assert server._coerce("hello") == "hello"


class TestMiniYamlLoad:
    def test_parse_flask_section(self):
        text = "flask:\n  host: 127.0.0.1\n  port: 8080\n"
        data = server._mini_yaml_load(text)
        assert data["flask"]["host"] == "127.0.0.1"
        assert data["flask"]["port"] == 8080

    def test_parse_tools_section(self):
        # 真实 config.yaml 使用行内流映射格式
        text = "tools:\n  read_file:      { enabled: true }\n  list_dir:       { enabled: false }\n"
        data = server._mini_yaml_load(text)
        assert data["tools"]["read_file"]["enabled"] is True
        assert data["tools"]["list_dir"]["enabled"] is False

    def test_parse_site_profiles(self):
        text = "site_profiles:\n  glm: profile_glm\n  deepseek: profile_ds\n"
        data = server._mini_yaml_load(text)
        assert data["site_profiles"]["glm"] == "profile_glm"
        assert data["site_profiles"]["deepseek"] == "profile_ds"

    def test_parse_top_level_default_profile(self):
        text = "default_profile: deepseek\n"
        data = server._mini_yaml_load(text)
        assert data["default_profile"] == "deepseek"

    def test_parse_comments_ignored(self):
        text = "# comment\nflask:\n  port: 3000  # inline comment\n"
        data = server._mini_yaml_load(text)
        assert data["flask"]["port"] == 3000

    def test_parse_empty_text(self):
        data = server._mini_yaml_load("")
        assert data["default_profile"] == "glm"
        assert data["tools"] == {}


class TestLoadYamlConfig:
    def test_load_yaml_config_missing_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(server, "CONFIG_PATH", tmp_path / "nonexistent.yaml")
        assert server._load_yaml_config() == {}

    def test_load_yaml_config_with_yaml(self, monkeypatch, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("flask:\n  port: 7777\n", encoding="utf-8")
        monkeypatch.setattr(server, "CONFIG_PATH", cfg)
        data = server._load_yaml_config()
        assert data["flask"]["port"] == 7777

    def test_load_yaml_config_yaml_parse_error_fallback(self, monkeypatch, tmp_path):
        """PyYAML 解析失败时应回退到内置解析。"""
        cfg = tmp_path / "config.yaml"
        cfg.write_text(": invalid yaml: [", encoding="utf-8")
        monkeypatch.setattr(server, "CONFIG_PATH", cfg)
        # 强制模拟 yaml 存在但解析失败
        original_yaml = server.yaml
        server.yaml = __import__("yaml")
        try:
            data = server._load_yaml_config()
            # 回退到 mini_yaml_load，解析结果至少包含默认键
            assert "flask" in data
            assert "tools" in data
        finally:
            server.yaml = original_yaml


class TestSaveConfigToYaml:
    def test_save_config_missing_file_returns_false(self, monkeypatch, tmp_path):
        monkeypatch.setattr(server, "CONFIG_PATH", tmp_path / "nonexistent.yaml")
        assert server.save_config_to_yaml() is False

    def test_save_config_writes_yaml(self, monkeypatch, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("flask:\n  port: 5000\n", encoding="utf-8")
        monkeypatch.setattr(server, "CONFIG_PATH", cfg)
        monkeypatch.setattr(server, "CONFIG", {
            "flask": {"host": "127.0.0.1", "port": 9000},
            "tools": {"read_file": {"enabled": False}},
            "default_profile": "glm",
            "site_profiles": {},
        })
        assert server.save_config_to_yaml() is True
        # 验证写盘内容含新端口
        content = cfg.read_text(encoding="utf-8")
        assert "9000" in content

    def test_save_config_without_yaml_fallback(self, monkeypatch, tmp_path):
        """无 PyYAML 时走行内修补分支（仅处理流式映射格式）。"""
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "flask:\n  port: 5000\ntools:\n  read_file:      { enabled: true }\n",
            encoding="utf-8")
        monkeypatch.setattr(server, "CONFIG_PATH", cfg)
        monkeypatch.setattr(server, "CONFIG", {
            "flask": {"host": "127.0.0.1", "port": 9000},
            "tools": {"read_file": {"enabled": False}},
            "default_profile": "glm",
            "site_profiles": {},
        })
        original_yaml = server.yaml
        server.yaml = None
        try:
            assert server.save_config_to_yaml() is True
            content = cfg.read_text(encoding="utf-8")
            assert "9000" in content
            assert "enabled: false" in content
        finally:
            server.yaml = original_yaml


class TestIsToolEnabled:
    def test_fix_tool_always_enabled(self):
        assert server.is_tool_enabled("read_tool_source") is True
        assert server.is_tool_enabled("hot_reload_fix") is True

    def test_missing_entry_defaults_true(self, monkeypatch):
        monkeypatch.setattr(server, "CONFIG", {
            "flask": {"host": "127.0.0.1", "port": 5000},
            "tools": {},
            "default_profile": "glm",
            "site_profiles": {},
        })
        assert server.is_tool_enabled("nonexistent_tool") is True

    def test_entry_enabled_false(self, monkeypatch):
        monkeypatch.setattr(server, "CONFIG", {
            "flask": {"host": "127.0.0.1", "port": 5000},
            "tools": {"read_file": {"enabled": False}},
            "default_profile": "glm",
            "site_profiles": {},
        })
        assert server.is_tool_enabled("read_file") is False
