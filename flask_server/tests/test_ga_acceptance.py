"""G-A 验收夹具（dispatcher-20261117T220214-d0f61c）：1a 后端标准接口与会话。

对 docs/split-mirror-and-tools-service.md 第七节阶段 1a 第 1/2/3 项与 6.1
工具结果内容约定做端到端实跑（验收报告见 docs/ga-1a-backend-acceptance.md，
逐项 pass/fail 与证据以报告为准）：

  S1 正常对话       纯文本轮：200、回声空文本、finish=stop、会话落盘
  S2 工具调用       意图来自 assistant.tool_calls，真实管线执行 write_to_file
  S3 工具结果回灌   已回填结果的全量历史重发，不重复执行（seed 反证）
  S4 多轮延续       同一 site_key 两轮：历史累加，旧历史原样保留
  S5 错误回传       未声明参数名 -> ToolParamError 信封进 content（6.1）
  S6 stream 拒绝    stream=true 明确 400，不静默降级
  SP System Prompt  GET /v1/system_prompt 四段齐序、方言与 schema 零泄漏

与 test_chat_api.py 的分工：那边是路由 / 存储的单元级断言（上游数据受控
注入）；本文件是验收视角的端到端联合装配（双蓝图同 app、system prompt
走真实数据源、6.1 信封字段形状逐键断言），主干行为两处互为印证。

执行口径与 test_chat_api.py 同源：runtime 四件套等价 _init_runtime 装配
（不经应用工厂时 DISPATCH 为空，工具调用一律 UnknownTool），会话存储与
写入目标全部重定向临时目录，不污染真实数据；装配用毕还原。
"""
import json
import sys
from pathlib import Path

import pytest

# flask_server 根：三个导入根与 test_chat_api.py 同口径（server / core / tools）
_SRV = Path(__file__).resolve().parents[1]
for _dir in (str(_SRV), str(_SRV / "core"), str(_SRV / "tools")):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)

import runtime                  # noqa: E402
import tools_impl               # noqa: E402
import chat_completions as cc   # noqa: E402
import system_prompt as sp      # noqa: E402
from flask import Flask         # noqa: E402
from routes.chat_api import bp as chat_api_bp            # noqa: E402
from routes.system_prompt import bp as system_prompt_bp  # noqa: E402


def _assistant_call(call_id, name, arguments):
    """构造带 tool_calls 的 assistant 消息（请求侧调用意图的标准形态）。"""
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": call_id, "type": "function",
         "function": {"name": name, "arguments": arguments}}]}


def _tool_msg(call_id, content):
    """构造已回填结果的 tool 消息（content 为信封 JSON 字符串）。"""
    return {"role": "tool", "tool_call_id": call_id, "name": "write_to_file",
            "content": json.dumps(content, ensure_ascii=False)}


def _write_args(path, content):
    """拼 write_to_file 的 arguments（JSON 对象字符串）。"""
    return json.dumps({"path": path, "content": content}, ensure_ascii=False)


@pytest.fixture()
def ga_env(tmp_path):
    """验收装配：runtime 四件套 + 存储重定向 + 双蓝图 app；用毕还原。"""
    orig = (runtime.impl, runtime.TOOLS, runtime.DISPATCH, runtime.CONFIG)
    store_dir = cc._STORE_DIR
    tools_on = {k: {"enabled": True} for k in tools_impl.TOOLS}
    runtime.impl = tools_impl
    runtime.TOOLS = dict(tools_impl.TOOLS)
    runtime.DISPATCH = dict(tools_impl.DISPATCH)
    cfg = dict(runtime.CONFIG or {})
    cfg["tools"] = tools_on
    runtime.CONFIG = cfg
    cc._STORE_DIR = str(tmp_path / "chat_sessions")
    app = Flask(__name__)
    app.register_blueprint(chat_api_bp)
    app.register_blueprint(system_prompt_bp)
    app.config["TESTING"] = True
    yield {"client": app.test_client(), "tmp": tmp_path}
    (runtime.impl, runtime.TOOLS, runtime.DISPATCH, runtime.CONFIG) = orig
    cc._STORE_DIR = store_dir


def _post_chat(env, payload):
    """POST /v1/chat/completions，返回 (status_code, 响应 JSON)。"""
    r = env["client"].post("/v1/chat/completions", json=payload)
    return r.status_code, r.get_json()


def _tool_messages(data):
    """取出响应 messages 里的 tool 结果序列。"""
    return [m for m in data["messages"] if m["role"] == "tool"]


# ---------- S1 正常对话（阶段 1a 第 1 项 / 场景 1） ----------

def test_s1_plain_round(ga_env):
    """纯文本轮：200、回声空文本（不代生成）、无工具、历史落盘。"""
    status, data = _post_chat(ga_env, {
        "site_key": "ga_s1",
        "messages": [{"role": "user", "content": "你好"}],
    })
    assert status == 200
    msg = data["choices"][0]["message"]
    assert msg["role"] == "assistant" and msg["content"] == ""
    assert data["choices"][0]["finish_reason"] == "stop"
    assert _tool_messages(data) == []
    assert (Path(cc._STORE_DIR) / "ga_s1.json").is_file(), "会话应按 site_key 落盘"


# ---------- S2 工具调用（阶段 1a 第 1 项 / 场景 2） ----------

def test_s2_tool_call(ga_env):
    """意图来自 assistant.tool_calls：真实管线执行并回传标准 tool 消息。"""
    target = ga_env["tmp"] / "s2.txt"
    status, data = _post_chat(ga_env, {
        "site_key": "ga_s2",
        "messages": [
            {"role": "user", "content": "帮我写文件"},
            _assistant_call("ga_call_s2", "write_to_file",
                            _write_args(target.as_posix(), "ga-s2")),
        ],
    })
    assert status == 200
    assert data["choices"][0]["finish_reason"] == "tool_calls"
    tms = _tool_messages(data)
    assert len(tms) == 1 and tms[0]["tool_call_id"] == "ga_call_s2"
    assert json.loads(tms[0]["content"])["success"] is True
    assert target.read_text(encoding="utf-8") == "ga-s2", "工具应真实执行"


# ---------- S3 工具结果回灌（阶段 1a 第 1 项 / 场景 3） ----------

def test_s3_result_replay(ga_env):
    """已回填结果的全量历史重发：不重复执行（seed 反证，文件不被重写）。"""
    target = ga_env["tmp"] / "s3.txt"
    target.write_text("seed", encoding="utf-8")
    history = [
        {"role": "user", "content": "帮我写文件"},
        _assistant_call("ga_call_s3", "write_to_file",
                        _write_args(target.as_posix(), "rewritten")),
        _tool_msg("ga_call_s3", {"success": True}),
    ]
    status, data = _post_chat(ga_env, {"site_key": "ga_s3", "messages": history})
    assert status == 200
    assert _tool_messages(data) == history[2:], "不得新增 tool 结果"
    assert data["choices"][0]["finish_reason"] == "stop"
    assert target.read_text(encoding="utf-8") == "seed", "已回填调用不得重放"


# ---------- S4 多轮延续（阶段 1a 第 1 项 / 场景 4） ----------

def test_s4_multi_round(ga_env):
    """同一 site_key 第二轮：历史累加，旧历史原样保留。"""
    st1, d1 = _post_chat(ga_env, {
        "site_key": "ga_s4",
        "messages": [{"role": "user", "content": "第一问"}],
    })
    assert st1 == 200
    st2, d2 = _post_chat(ga_env, {
        "site_key": "ga_s4",
        "messages": [{"role": "user", "content": "第二问"}],
    })
    assert st2 == 200
    n1 = len(d1["messages"])
    assert len(d2["messages"]) > n1, "历史应累加"
    assert d2["messages"][:n1] == d1["messages"], "旧历史应原样保留"


# ---------- S5 错误回传（阶段 1a 第 1 项 / 场景 5；6.1 信封约定） ----------

def test_s5_error_envelope(ga_env):
    """未声明参数名：ToolParamError 信封以 JSON 字符串进 content（6.1）。"""
    target = ga_env["tmp"] / "s5.txt"
    status, data = _post_chat(ga_env, {
        "site_key": "ga_s5",
        "messages": [
            {"role": "user", "content": "写文件"},
            _assistant_call("ga_call_s5", "write_to_file",
                            json.dumps({"path": target.as_posix(),
                                        "content": "y",
                                        "undeclared_param": 1})),
        ],
    })
    assert status == 200, "工具失败不得变成 HTTP 500"
    tms = _tool_messages(data)
    assert len(tms) == 1 and tms[0]["tool_call_id"] == "ga_call_s5"
    extra = set(tms[0]) - {"role", "tool_call_id", "name", "content"}
    assert not extra, "tool 消息不得有 content 以外的扩展字段（6.1）"
    body = json.loads(tms[0]["content"])
    assert body["success"] is False
    assert body["errorType"] == "ToolParamError"
    assert body["origin"] == "parameter"
    assert body.get("hint"), "错误信封应带 hint"
    assert "path" in body.get("available", []), "应附合法参数名清单"


# ---------- S6 stream=true 明确报错（不静默降级） ----------

def test_s6_stream_rejected(ga_env):
    """stream=true：HTTP 400 + code=stream_not_supported。"""
    status, data = _post_chat(ga_env, {
        "site_key": "ga_s6",
        "messages": [{"role": "user", "content": "你好"}],
        "stream": True,
    })
    assert status == 400
    assert data["error"]["code"] == "stream_not_supported"


# ---------- SP /v1/system_prompt 四段边界（阶段 1a 第 2 项，真实数据源） ----------

def test_sp_system_prompt_boundary(ga_env):
    """四段标记齐备且顺序固定；方言词与参数 schema 零泄漏（真实数据源）。"""
    r = ga_env["client"].get("/v1/system_prompt")
    assert r.status_code == 200
    data = r.get_json()
    text = data["system_prompt"]
    marks = (sp.MARK_IDENTITY, sp.MARK_RULES, sp.MARK_SKILLS, sp.MARK_PARAMS)
    idx = [text.find(m) for m in marks]
    assert all(i >= 0 for i in idx), "四段标记必须齐备"
    assert idx == sorted(idx), "顺序必须：身份 -> 规则 -> 技能 -> 通则"
    assert len(data["sections"]) == 4
    for w in ("回传格式", "朗读", "语音朗读", "选择器", "方言",
              "语言包", "翻译员", "调用格式"):
        assert w not in text, "方言词泄漏：%s" % w
    for w in ("properties", "required", "anyOf", '"type": "object"'):
        assert w not in text, "参数 schema 泄漏：%s" % w
    assert "get_tool_params" in text, "通则段应要求先查参数"