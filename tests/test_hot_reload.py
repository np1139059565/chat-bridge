"""热重载与 AI 自愈工具测试。"""
import os
import shutil
from pathlib import Path

import pytest

import server


@pytest.fixture
def impl_backup():
    """备份真实 tools_impl.py，测试结束后恢复并热重载。"""
    real_impl = Path(server.impl.__file__)
    backup = real_impl.read_text(encoding="utf-8")
    yield real_impl, backup
    # 恢复原始内容
    real_impl.write_text(backup, encoding="utf-8")
    server._reload_impl()


class TestReadToolSource:
    def test_read_existing_tool_source(self, app):
        result = server.t_read_tool_source({"tool": "list_dir"})
        assert result["tool"] == "list_dir"
        assert "def t_list_dir" in result["source"]

    def test_read_unknown_tool_raises(self, app):
        with pytest.raises(server.impl.ToolParamError):
            server.t_read_tool_source({"tool": "nonexistent"})

    def test_read_missing_tool_param_raises(self, app):
        with pytest.raises(server.impl.ToolParamError):
            server.t_read_tool_source({})


class TestHotReloadFix:
    def test_patch_success(self, app, impl_backup):
        real_impl, original = impl_backup
        marker = "def t_list_dir(p):"
        assert marker in original

        result = server.t_hot_reload_fix({
            "old_str": marker,
            "new_str": marker + "  # test-patch\n",
        })
        assert result["patched"] is True
        assert result["reloaded"] is True
        # 补丁应已应用到模块源码
        assert "# test-patch" in real_impl.read_text(encoding="utf-8")

    def test_patch_invalid_code_rolls_back(self, app, impl_backup):
        real_impl, original = impl_backup

        result = server.t_hot_reload_fix({
            "old_str": "def t_list_dir(p):",
            "new_str": "def t_list_dir(p)::::",
        })
        assert result["patched"] is False
        assert result["rolledBack"] is True
        # 回滚后源码应恢复
        assert real_impl.read_text(encoding="utf-8") == original

    def test_patch_old_str_not_found_raises(self, app, impl_backup):
        real_impl, original = impl_backup
        with pytest.raises(server.impl.ToolParamError):
            server.t_hot_reload_fix({
                "old_str": "this_string_does_not_exist_anywhere_12345",
                "new_str": "x",
            })


class TestErrorClassification:
    def test_classify_parameter_error(self, app):
        err = server.impl.ToolParamError("test")
        assert server.classify_error(err) == "parameter"

    def test_classify_environment_error(self, app):
        assert server.classify_error(FileNotFoundError("test")) == "environment"
        assert server.classify_error(PermissionError("test")) == "environment"

    def test_classify_unknown_error(self, app):
        assert server.classify_error(RuntimeError("test")) == "tool_internal"

    def test_classify_value_error_as_parameter(self, app):
        assert server.classify_error(ValueError("test")) == "parameter"
