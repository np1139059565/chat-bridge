"""pytest 公共夹具：路径注入、Flask test client、临时 skill、配置隔离。"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FLASK_DIR = ROOT / "flask_server"
sys.path.insert(0, str(FLASK_DIR))


@pytest.fixture
def app(monkeypatch):
    """Flask 测试客户端；隔离 config.yaml 写入与 CONFIG 状态。"""
    import server

    # 隔离写回：测试期间不落盘真实 config.yaml
    monkeypatch.setattr(server, "save_config_to_yaml", lambda: True)
    # 隔离读入：每个测试从空配置开始，避免真实 config.yaml 干扰
    monkeypatch.setattr(server, "_load_yaml_config", lambda: {})

    # 重建干净状态
    server._reload_impl()
    server.CONFIG = server._init_config()
    server.app.config["TESTING"] = True
    client = server.app.test_client()

    yield client

    # monkeypatch 会在测试后自动 undo；这里显式恢复服务状态
    server._reload_impl()
    server.CONFIG = server._init_config()


@pytest.fixture
def tools_impl():
    """直接导入内置工具实现模块，便于函数级测试。"""
    import tools_impl
    return tools_impl


@pytest.fixture
def tmp_skill_dir(tmp_path):
    """在临时目录创建一个最小标准 skill，返回其路径。"""
    skill_dir = tmp_path / "demo_skill"
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    return skill_dir


@pytest.fixture
def skill_with_echo(tmp_skill_dir):
    """写一个可执行 echo 脚本的 skill，返回 (skill_dir, tool_json_dict)。"""
    tool_json = {
        "tools": [{
            "name": "demo_echo",
            "description": "回声测试工具 # 含井号",
            "script": "scripts/echo.py",
            "interpreter": "python",
            "arg_style": "flag",
            "parameters": [
                {"name": "msg", "type": "string", "required": True, "description": "回显内容"},
                {"name": "repeat", "type": "boolean", "required": False, "description": "重复"}
            ]
        }]
    }
    (tmp_skill_dir / "tool.json").write_text(
        json.dumps(tool_json, ensure_ascii=False), encoding="utf-8")
    (tmp_skill_dir / "scripts" / "echo.py").write_text(
        "import sys, json\n"
        "args = sys.argv[1:]\n"
        "out = {}\n"
        "i = 0\n"
        "while i < len(args):\n"
        "    if args[i] == '--msg':\n"
        "        out['msg'] = args[i+1]; i += 2\n"
        "    elif args[i] == '--repeat':\n"
        "        out['repeat'] = True; i += 1\n"
        "    else:\n"
        "        i += 1\n"
        "if out.get('repeat'):\n"
        "    out['msg'] = out.get('msg','') * 2\n"
        "print(json.dumps(out, ensure_ascii=False))\n",
        encoding="utf-8")
    return tmp_skill_dir, tool_json


@pytest.fixture(autouse=True)
def _isolate_custom_tools(tmp_path, monkeypatch):
    """每个测试都使用独立的 custom_tools.yaml，避免污染真实文件。"""
    import custom_tools as ct
    tmp_ct = tmp_path / "custom_tools.yaml"
    monkeypatch.setattr(ct, "CT_PATH", tmp_ct)
    return tmp_ct
