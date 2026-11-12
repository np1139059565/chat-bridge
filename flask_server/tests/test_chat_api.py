"""标准对话接口测试（A-1 六场景 + A-4 标准链路语义）。

阶段 2 语义（docs/split-mirror-and-tools-service.md 3.1 / 3.9 / 4.4、决策 2）：
- 调用意图只来自请求侧 assistant.tool_calls；服务端不生成 assistant 文本，
  占位生成器已整体移除；
- 服务端执行历史中尚未回填结果的调用（按 tool_call_id 配对防重放，
  重发全量历史幂等；并行多调用逐个执行按序回传；无 id 调用跳过）；
- choices.message 是合并历史末条 assistant 的回声，finish_reason 按
  本轮是否执行了工具取 tool_calls / stop。

- 不依赖 app.py 的应用工厂：构造独立 Flask app 只注册 chat_api_bp；
- 会话存储重定向到 tmp_path（monkeypatch chat_completions._STORE_DIR，
  模块对象与 routes.chat_api 引用的是同一个，见顶层 import 的一致性）；
- 工具执行走真实管线：write_to_file 落盘到 tmp_path 验证成功信封，
  缺参 / 非法 JSON 触发 ToolParamError 信封验证错误分类字段。
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


def assistant_call(call_id, name, arguments):
    """构造带 tool_calls 的 assistant 消息（请求侧调用意图的标准形态）。"""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": call_id, "type": "function",
             "function": {"name": name, "arguments": arguments}}
        ],
    }


def tool_msg(call_id, content):
    """构造 tool 结果消息（content 为信封 JSON 字符串）。"""
    return {"role": "tool", "tool_call_id": call_id, "name": "write_to_file",
            "content": json.dumps(content, ensure_ascii=False)}


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
    返回 UnknownTool，场景 2 的 write_to_file 无法走真实执行管线。
    必须像 test_routes_integration._RouteBase.setUp 一样补齐四件事：
    impl / TOOLS / DISPATCH / CONFIG["tools"] 全量 enabled，缺一不可。
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


# ---------- 场景 1：纯文本对话（无工具、无调用意图） ----------

def test_plain_text_round(client, store_dir):
    r = post(client, {"site_key": "t-plain-1", "messages": [{"role": "user", "content": "你好"}]})
    assert r.status_code == 200
    data = r.get_json()
    msg = data["choices"][0]["message"]
    assert msg["role"] == "assistant"
    assert msg["content"] == "", "无 assistant 历史时回声为空文本，不代生成"
    assert not msg.get("tool_calls")
    assert data["choices"][0]["finish_reason"] == "stop"
    assert "tool" not in [m["role"] for m in data["messages"]]
    # 会话已按 site_key 落盘
    assert (store_dir / "t-plain-1.json").is_file()


# ---------- 场景 2：单轮带一个工具调用（意图来自 assistant.tool_calls） ----------

def _assert_call_a1_echo(data):
    """断言 choices.message 回声末条 assistant：单调用 call_a1、finish_reason=tool_calls。"""
    msg = data["choices"][0]["message"]
    assert msg["role"] == "assistant"
    assert msg.get("tool_calls"), "choices.message 回声末条 assistant（含调用）"
    assert msg["tool_calls"][0]["id"] == "call_a1"
    assert data["choices"][0]["finish_reason"] == "tool_calls"


def _assert_call_a1_result(data, target):
    """断言服务端已执行工具：响应含 1 条 tool 结果、文件内容正确。"""
    tms = tool_messages(data)
    assert len(tms) == 1
    assert tms[0]["tool_call_id"] == "call_a1"
    assert json.loads(tms[0]["content"]).get("success") is True
    assert target.read_text(encoding="utf-8") == "hi from chat api"


def test_single_tool_call(client, store_dir, tmp_path):
    target = tmp_path / "hello.txt"
    r = post(
        client,
        {
            "site_key": "t-tool-1",
            "messages": [
                {"role": "user", "content": "帮我写文件"},
                assistant_call(
                    "call_a1", "write_to_file",
                    json.dumps({"path": target.as_posix(), "content": "hi from chat api"},
                               ensure_ascii=False),
                ),
            ],
            "tools": TOOLS_DECL,
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    _assert_call_a1_echo(data)
    _assert_call_a1_result(data, target)
    # 落盘历史含请求侧 assistant 调用与 tool 结果
    roles = [m["role"] for m in data["messages"]]
    assert roles == ["user", "assistant", "tool"]


def test_parallel_tool_calls(client, store_dir, tmp_path):
    """并行多调用：一次声明两个调用，逐个执行、按序回传（规格 3.1）。"""
    t1 = tmp_path / "p1.txt"
    t2 = tmp_path / "p2.txt"
    msgs = [
        {"role": "user", "content": "写两个文件"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_p1", "type": "function",
                 "function": {"name": "write_to_file",
                              "arguments": json.dumps({"path": t1.as_posix(), "content": "one"})}},
                {"id": "call_p2", "type": "function",
                 "function": {"name": "write_to_file",
                              "arguments": json.dumps({"path": t2.as_posix(), "content": "two"})}},
            ],
        },
    ]
    r = post(client, {"site_key": "t-parallel-1", "messages": msgs, "tools": TOOLS_DECL})
    assert r.status_code == 200
    data = r.get_json()
    assert data["choices"][0]["finish_reason"] == "tool_calls"
    tms = tool_messages(data)
    assert [m["tool_call_id"] for m in tms] == ["call_p1", "call_p2"]
    assert t1.read_text(encoding="utf-8") == "one"
    assert t2.read_text(encoding="utf-8") == "two"


def test_duplicate_call_id_executed_once(client, store_dir, tmp_path):
    """同一 tool_call_id 重复声明：只执行首次，防重放。"""
    t1 = tmp_path / "d1.txt"
    t2 = tmp_path / "d2.txt"
    call = lambda p: {"id": "call_d1", "type": "function",
                      "function": {"name": "write_to_file",
                                   "arguments": json.dumps({"path": p.as_posix(), "content": "x"})}}
    msgs = [
        {"role": "user", "content": "写文件"},
        {"role": "assistant", "content": None, "tool_calls": [call(t1), call(t2)]},
    ]
    r = post(client, {"site_key": "t-dup-1", "messages": msgs, "tools": TOOLS_DECL})
    assert r.status_code == 200
    tms = tool_messages(r.get_json())
    assert len(tms) == 1 and tms[0]["tool_call_id"] == "call_d1"
    assert t1.is_file() and not t2.exists()


def test_replayed_history_not_reexecuted(client, store_dir, tmp_path):
    """防重放：已回填结果的调用随全量历史重发，不再执行。"""
    target = tmp_path / "replay.txt"
    # 断言设计：文件先以首轮执行产物存在（内容 seed）；历史里调用的
    # arguments 是 content=rewritten——若被错误重放，文件会被改写成
    # rewritten；正确行为是跳过执行，文件保持 seed 不动。
    target.write_text("seed", encoding="utf-8")
    seeded = [
        {"role": "user", "content": "帮我写文件"},
        assistant_call(
            "call_z1", "write_to_file",
            json.dumps({"path": target.as_posix(), "content": "rewritten"}, ensure_ascii=False),
        ),
        tool_msg("call_z1", {"success": True}),
    ]
    cc.save_session("t-replay-1", seeded)
    r = post(client, {"site_key": "t-replay-1", "messages": seeded, "tools": TOOLS_DECL})
    assert r.status_code == 200
    data = r.get_json()
    assert tool_messages(data) == seeded[2:], "已有结果的调用不重复执行"
    assert data["choices"][0]["finish_reason"] == "stop"
    assert target.read_text(encoding="utf-8") == "seed", "文件未被重写"


def test_call_without_id_is_skipped(client, store_dir, tmp_path):
    """无 id 的调用无法与 tool 结果配对，跳过不执行（否则每轮重放）。"""
    target = tmp_path / "noid.txt"
    msgs = [
        {"role": "user", "content": "写文件"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"type": "function",
                         "function": {"name": "write_to_file",
                                      "arguments": json.dumps({"path": target.as_posix(), "content": "x"})}}]},
    ]
    r = post(client, {"site_key": "t-noid-1", "messages": msgs, "tools": TOOLS_DECL})
    assert r.status_code == 200
    data = r.get_json()
    assert tool_messages(data) == []
    assert data["choices"][0]["finish_reason"] == "stop"
    assert not target.exists()


# ---------- 场景 3：工具结果回灌，不再重复执行 ----------

def test_tool_result_followup(client, store_dir):
    msgs = [
        {"role": "user", "content": "查一下再写"},
        assistant_call("call_x1", "write_to_file", "{}"),
        tool_msg("call_x1", {"success": True}),
    ]
    r = post(client, {"site_key": "t-follow-1", "messages": msgs, "tools": TOOLS_DECL})
    assert r.status_code == 200
    data = r.get_json()
    msg = data["choices"][0]["message"]
    assert msg["role"] == "assistant"
    assert msg.get("tool_calls"), "回声末条 assistant（调用已回填，不再执行）"
    assert data["choices"][0]["finish_reason"] == "stop"
    assert tool_messages(data) == msgs[2:], "不新增 tool 结果"


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
            "messages": [
                {"role": "user", "content": "写文件"},
                assistant_call("call_e1", "write_to_file", "{}"),
            ],
            "tools": TOOLS_DECL,
        },
    )
    assert r.status_code == 200, "工具失败不应导致 HTTP 500"
    data = r.get_json()
    tms = tool_messages(data)
    assert len(tms) == 1
    assert tms[0]["tool_call_id"] == "call_e1"
    assert isinstance(tms[0]["content"], str), "tool content 必须是 JSON 字符串"
    body = json.loads(tms[0]["content"])
    assert body.get("success") is False
    assert body.get("errorType"), "信封应含错误分类字段（决策 10）"


def test_invalid_arguments_envelope(client, store_dir):
    """arguments 非法 JSON：ToolParamError 信封，不产生 500。"""
    r = post(
        client,
        {
            "site_key": "t-badargs-1",
            "messages": [
                {"role": "user", "content": "写文件"},
                assistant_call("call_b1", "write_to_file", "{bad json"),
            ],
            "tools": TOOLS_DECL,
        },
    )
    assert r.status_code == 200
    tms = tool_messages(r.get_json())
    assert len(tms) == 1 and tms[0]["tool_call_id"] == "call_b1"
    body = json.loads(tms[0]["content"])
    assert body.get("success") is False
    assert body.get("errorType") == "ToolParamError"
    assert body.get("origin") == "parameter"


def test_unknown_tool_envelope(client, store_dir):
    """未声明也未实现的工具：404 信封含 available 清单。"""
    r = post(
        client,
        {
            "site_key": "t-unknown-1",
            "messages": [
                {"role": "user", "content": "调用"},
                assistant_call("call_u1", "write_to_file_typo", "{}"),
            ],
            "tools": TOOLS_DECL,
        },
    )
    assert r.status_code == 200
    body = json.loads(tool_messages(r.get_json())[0]["content"])
    assert body.get("success") is False
    assert "write_to_file" in body.get("available", [])


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


def test_tools_must_be_array(client, store_dir):
    r = post(client, {"site_key": "t-bad-3", "messages": [{"role": "user", "content": "hi"}], "tools": 42})
    assert r.status_code == 400
    assert "tools 必须是数组" in r.get_json()["error"]["message"]


def test_generated_site_key_returned(client, store_dir):
    r = post(client, {"messages": [{"role": "user", "content": "你好"}]})
    assert r.status_code == 200
    data = r.get_json()
    assert data["site_key"], "未携带 site_key 时应生成并返回"
