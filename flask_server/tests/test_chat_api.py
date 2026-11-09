"""标准对话接口测试（任务 A-1）：覆盖验收文档的六个场景 + 请求校验。

- 不依赖 app.py 的应用工厂：构造独立 Flask app 只注册 chat_api_bp；
- 会话存储重定向到 tmp_path（monkeypatch chat_completions._STORE_DIR，
  模块对象与 routes.chat_api 引用的是同一个，见顶层 import 的一致性）；
- 工具执行走真实管线：write_to_file 落盘到 tmp_path 验证成功信封，
  缺参触发 ToolParamError 信封验证错误分类字段。
"""

import json
import sys
from pathlib import Path

import pytest

# 导入路径自备：conftest.py 只重定向运行时状态、不做路径修正。本文件顶层
# import 的模块分布在 flask_server 根（runtime）、core/（chat_completions）、
# tools/（tools_impl）三处，必须在收集期（早于一切夹具执行）就放进
# sys.path，不依赖其它测试文件恰好先被收集导入。
_BASE = Path(__file__).resolve().parents[1]
for _entry in (str(_BASE), str(_BASE / "core"), str(_BASE / "tools")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import chat_completions as cc    # noqa: E402
import runtime                   # noqa: E402
import tools_impl                # noqa: E402
from flask import Flask          # noqa: E402
from routes.chat_api import bp as chat_api_bp   # noqa: E402


TOOLS_DECL = [
    {
        "type": "function",
        "function": {
            "name": "write_to_file",
            "description": "创建或覆盖写入完整文件内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    }
]


@pytest.fixture()
def store_dir(tmp_path, monkeypatch):
    """把会话存储重定向到临时目录，避免污染真实数据目录。"""
    d = tmp_path / "chat_sessions"
    monkeypatch.setattr(cc, "_STORE_DIR", str(d))
    return d


@pytest.fixture(autouse=True)
def _init_runtime_tables():
    """初始化运行时工具表（等价于 create_app 的 _init_runtime）。

    为什么需要：本文件的 client fixture 不经过 app.py 的应用工厂，
    runtime.DISPATCH / runtime.CONFIG 保持初始空值。此时工具调用一律
    返回 UnknownTool（场景 2 失败），is_tool_enabled 因缺配置而判下线。
    必须像 test_routes_integration._RouteBase.setUp 一样补齐四件事：
    impl / TOOLS / DISPATCH / CONFIG["tools"] 全量 enabled，
    缺一则场景 2 的 write_to_file 无法走真实执行管线。
    """
    _orig = (runtime.impl, runtime.TOOLS, runtime.DISPATCH, runtime.CONFIG)
    runtime.impl = tools_impl
    runtime.TOOLS = dict(tools_impl.TOOLS)
    runtime.DISPATCH = dict(tools_impl.DISPATCH)
    cfg = dict(runtime.CONFIG or {})
    cfg["tools"] = {k: {"enabled": True} for k in runtime.TOOLS}
    runtime.CONFIG = cfg
    yield
    runtime.impl, runtime.TOOLS, runtime.DISPATCH, runtime.CONFIG = _orig


@pytest.fixture()
def client():
    app = Flask(__name__)
    app.register_blueprint(chat_api_bp)
    app.config["TESTING"] = True
    return app.test_client()


def post(client, payload):
    return client.post("/v1/chat/completions", json=payload)


def tool_messages(data):
    return [m for m in data["messages"] if m["role"] == "tool"]


# ---------- 场景 1：单轮纯文本对话 ----------

def test_plain_text_round(client, store_dir):
    r = post(client, {"site_key": "t-plain-1", "messages": [{"role": "user", "content": "你好"}]})
    assert r.status_code == 200
    data = r.get_json()
    msg = data["choices"][0]["message"]
    assert msg["role"] == "assistant"
    assert isinstance(msg["content"], str) and msg["content"]
    assert not msg.get("tool_calls")
    assert "tool" not in [m["role"] for m in data["messages"]]
    # 会话已按 site_key 落盘
    assert (store_dir / "t-plain-1.json").is_file()


# ---------- 场景 2：单轮带一个工具调用 ----------

def test_single_tool_call(client, store_dir, tmp_path):
    target = tmp_path / "hello.txt"
    user_text = 'write_to_file({"path": "%s", "content": "hi from chat api"})' % target.as_posix()
    r = post(
        client,
        {
            "site_key": "t-tool-1",
            "messages": [{"role": "user", "content": user_text}],
            "tools": TOOLS_DECL,
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    msg = data["choices"][0]["message"]
    assert msg["role"] == "assistant"
    assert msg.get("tool_calls"), "assistant 消息应含 tool_calls"
    call = msg["tool_calls"][0]
    assert call["function"]["name"] == "write_to_file"
    # 服务端已执行工具：响应 messages 含 tool 结果，且文件真实落盘
    tms = tool_messages(data)
    assert len(tms) == 1
    body = json.loads(tms[0]["content"])
    assert body.get("success") is True
    assert target.is_file()
    assert target.read_text(encoding="utf-8") == "hi from chat api"


# ---------- 场景 3：工具结果回灌，能继续生成下一轮 ----------

def test_tool_result_followup(client, store_dir):
    msgs = [
        {"role": "user", "content": 'write_to_file({"path": "x"})'},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_x1",
                    "type": "function",
                    "function": {"name": "write_to_file", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_x1",
            "name": "write_to_file",
            "content": "{\"success\": true}",
        },
    ]
    r = post(client, {"site_key": "t-follow-1", "messages": msgs, "tools": TOOLS_DECL})
    assert r.status_code == 200
    msg = r.get_json()["choices"][0]["message"]
    assert msg["role"] == "assistant"
    assert isinstance(msg.get("content"), str) and msg["content"]
    assert not msg.get("tool_calls"), "工具结果之后应出文本，不应再次触发工具"


# ---------- 场景 4：同一 site_key 多轮延续，历史累加 ----------

def test_multi_round_site_key(client, store_dir):
    r1 = post(client, {"site_key": "t-multi-1", "messages": [{"role": "user", "content": "第一问"}]})
    assert r1.status_code == 200
    n1 = len(r1.get_json()["messages"])

    r2 = post(client, {"site_key": "t-multi-1", "messages": [{"role": "user", "content": "第二问"}]})
    assert r2.status_code == 200
    data2 = r2.get_json()
    assert len(data2["messages"]) > n1, "历史应被累加"
    assert data2["messages"][:n1] == r1.get_json()["messages"], "旧历史应原样保留"


# ---------- 场景 5：stream=true 明确报错，不静默降级 ----------

def test_stream_rejected(client, store_dir):
    r = post(
        client,
        {
            "site_key": "t-stream-1",
            "messages": [{"role": "user", "content": "你好"}],
            "stream": True,
        },
    )
    assert r.status_code == 400
    err = r.get_json()["error"]
    assert err["code"] == "stream_not_supported"


# ---------- 场景 6：工具执行出错，content 是 JSON 字符串含错误分类字段 ----------

def test_tool_error_envelope(client, store_dir):
    r = post(
        client,
        {
            "site_key": "t-err-1",
            "messages": [{"role": "user", "content": "write_to_file({})"}],
            "tools": TOOLS_DECL,
        },
    )
    assert r.status_code == 200, "工具失败不应导致 HTTP 500"
    data = r.get_json()
    tms = tool_messages(data)
    assert len(tms) == 1
    assert isinstance(tms[0]["content"], str), "tool content 必须是 JSON 字符串"
    body = json.loads(tms[0]["content"])
    assert body.get("success") is False
    assert body.get("errorType"), "信封应含错误分类字段（决策 10）"


# ---------- 请求校验 ----------

def test_invalid_role_rejected(client, store_dir):
    r = post(client, {"site_key": "t-bad-1", "messages": [{"role": "robot", "content": "hi"}]})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_missing_messages_rejected(client, store_dir):
    r = post(client, {"site_key": "t-bad-2", "messages": []})
    assert r.status_code == 400


def test_invalid_site_key_rejected(client, store_dir):
    r = post(client, {"site_key": "bad key!", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 400


def test_generated_site_key_returned(client, store_dir):
    r = post(client, {"messages": [{"role": "user", "content": "你好"}]})
    assert r.status_code == 200
    data = r.get_json()
    assert data["site_key"], "未携带 site_key 时应生成并返回"