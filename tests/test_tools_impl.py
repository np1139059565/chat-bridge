"""内置工具实现 tools_impl.py 的单元测试。

注意：tools_impl 支持热重载（其它测试会 importlib.reload），
因此不能在模块级缓存 ToolParamError / 工具函数，
必须每次从 sys.modules 获取当前生效的模块对象。
"""
import sys

import pytest


def _impl():
    """返回当前生效的 tools_impl 模块（可能已被热重载替换）。"""
    return sys.modules["tools_impl"]


def _t_list_dir(p):
    return _impl().t_list_dir(p)


def _t_search_file(p):
    return _impl().t_search_file(p)


def _t_search_content(p):
    return _impl().t_search_content(p)


def _t_read_file(p):
    return _impl().t_read_file(p)


def _t_replace_in_file(p):
    return _impl().t_replace_in_file(p)


def _t_write_to_file(p):
    return _impl().t_write_to_file(p)


def _t_delete_file(p):
    return _impl().t_delete_file(p)


def _t_get_tool_params(p):
    return _impl().t_get_tool_params(p)


@pytest.fixture(autouse=True)
def _ensure_impl_loaded():
    """确保 tools_impl 已加载（收集阶段 sys.path 可能尚未完全就绪）。"""
    import tools_impl  # noqa: F401
    return _impl()


class TestParamValidation:
    def test_list_dir_missing_target_directory_raises(self):
        with pytest.raises(_impl().ToolParamError):
            _t_list_dir({})

    def test_list_dir_wrong_alias_path_raises(self):
        with pytest.raises(_impl().ToolParamError):
            _t_list_dir({"path": "flask_server"})

    def test_read_file_missing_filepath_raises(self):
        with pytest.raises(_impl().ToolParamError):
            _t_read_file({})

    def test_write_to_file_missing_content_raises(self):
        with pytest.raises(_impl().ToolParamError):
            _t_write_to_file({"filePath": "x"})

    def test_delete_file_missing_target_raises(self):
        with pytest.raises(_impl().ToolParamError):
            _t_delete_file({})


class TestListDir:
    def test_list_dir_returns_files_and_dirs(self, tmp_path):
        (tmp_path / "file.txt").write_text("hello", encoding="utf-8")
        (tmp_path / "subdir").mkdir()
        (tmp_path / ".hidden").mkdir()
        result = _t_list_dir({"target_directory": str(tmp_path)})
        assert result["directory"] == str(tmp_path)
        names = {item["name"] for item in result["items"]}
        assert "file.txt" in names
        assert "subdir" in names
        assert ".hidden" not in names

    def test_list_dir_ignore_globs(self, tmp_path):
        (tmp_path / "a.py").write_text("x", encoding="utf-8")
        (tmp_path / "b.txt").write_text("x", encoding="utf-8")
        result = _t_list_dir({"target_directory": str(tmp_path), "ignore_globs": ["*.py"]})
        names = {item["name"] for item in result["items"]}
        assert "a.py" not in names
        assert "b.txt" in names


class TestSearchFile:
    def test_search_file_recursive(self, tmp_path):
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("x", encoding="utf-8")
        result = _t_search_file({"target_directory": str(tmp_path), "pattern": "*.txt"})
        assert result["count"] == 2

    def test_search_file_non_recursive(self, tmp_path):
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("x", encoding="utf-8")
        result = _t_search_file({"target_directory": str(tmp_path), "pattern": "*.txt", "recursive": False})
        assert result["count"] == 1


class TestSearchContent:
    def test_search_content_finds_match(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("print('hello')\nprint('world')\n", encoding="utf-8")
        result = _t_search_content({"pattern": "hello", "path": str(tmp_path)})
        assert result["count"] == 1
        assert result["matches"][0]["line"] == 1

    def test_search_content_glob_filter(self, tmp_path):
        (tmp_path / "a.py").write_text("hello", encoding="utf-8")
        (tmp_path / "b.txt").write_text("hello", encoding="utf-8")
        result = _t_search_content({"pattern": "hello", "path": str(tmp_path), "glob": "*.py"})
        assert result["count"] == 1

    def test_search_content_case_insensitive_default(self, tmp_path):
        (tmp_path / "a.txt").write_text("Hello", encoding="utf-8")
        result = _t_search_content({"pattern": "hello", "path": str(tmp_path)})
        assert result["count"] == 1

    def test_search_content_case_sensitive(self, tmp_path):
        (tmp_path / "a.txt").write_text("Hello", encoding="utf-8")
        result = _t_search_content({"pattern": "hello", "path": str(tmp_path), "caseSensitive": True})
        assert result["count"] == 0


class TestReadFile:
    def test_read_file_full(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")
        result = _t_read_file({"filePath": str(f)})
        assert result["total_lines"] == 3
        assert result["content"] == "line1\nline2\nline3\n"

    def test_read_file_offset_limit(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("a\nb\nc\nd\n", encoding="utf-8")
        result = _t_read_file({"filePath": str(f), "offset": 2, "limit": 2})
        assert result["content"] == "b\nc\n"

    def test_read_file_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            _t_read_file({"filePath": "nonexistent_file_xyz"})


class TestReplaceInFile:
    def test_replace_in_file_success(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("hello world", encoding="utf-8")
        result = _t_replace_in_file({"filePath": str(f), "old_str": "world", "new_str": "there"})
        assert result["replaced"] is True
        assert f.read_text(encoding="utf-8") == "hello there"

    def test_replace_in_file_empty_old_raises(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("hello", encoding="utf-8")
        with pytest.raises(_impl().ToolParamError):
            _t_replace_in_file({"filePath": str(f), "old_str": "", "new_str": "x"})

    def test_replace_in_file_not_found_raises(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("hello", encoding="utf-8")
        with pytest.raises(_impl().ToolParamError):
            _t_replace_in_file({"filePath": str(f), "old_str": "nonexistent", "new_str": "x"})

    def test_replace_in_file_non_unique_raises(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("cat cat", encoding="utf-8")
        with pytest.raises(_impl().ToolParamError):
            _t_replace_in_file({"filePath": str(f), "old_str": "cat", "new_str": "dog"})


class TestWriteDeleteFile:
    def test_write_to_file_creates_parents(self, tmp_path):
        target = tmp_path / "nested" / "dir" / "file.txt"
        result = _t_write_to_file({"filePath": str(target), "content": "hello"})
        assert result["written"] is True
        assert target.read_text(encoding="utf-8") == "hello"

    def test_delete_file(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("hello", encoding="utf-8")
        result = _t_delete_file({"target_file": str(f)})
        assert result["deleted"] is True
        assert not f.exists()


class TestGetToolParams:
    def test_get_tool_params_existing(self):
        result = _t_get_tool_params({"tool_id": "list_dir"})
        assert result["tool"] == "list_dir"
        assert result["parameters"][0]["name"] == "target_directory"

    def test_get_tool_params_unknown(self):
        result = _t_get_tool_params({"tool_id": "nonexistent"})
        assert "error" in result
