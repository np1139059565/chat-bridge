"""任务 A-1 验收脚本：标准对话接口六类场景实测。

为什么独立于 pytest：验收要的是「对着 HTTP 接口逐场景打一遍」的可读
输出，任何人拉下分支即可直接运行复核，不需要先了解测试夹具的构造。

与 tests/test_chat_api.py 的分工：测试文件覆盖回归细节（校验分支与
边界形态），本脚本只走验收表列出的六类主路径，逐场景打印 PASS/FAIL。

运行（两种位置均可）：
    python scripts/check_chat_api.py              在 flask_server 下
    python flask_server/scripts/check_chat_api.py 在工程根下

退出码：0 = 六场景全部通过；1 = 存在失败。
"""

import json
import sys
import tempfile
from pathlib import Path

# 导入引导：脚本可能从工程根或 flask_server 下启动，先把 flask_server
# 根目录放进 sys.path；core/ tools/ 子目录由 runtime -> paths 补齐
# （与 app.py 的导入顺序约定一致）。
_SERVER_ROOT = Path(__file__).resolve().parent.parent
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

import runtime                 # noqa: E402
import tools_impl               # noqa: E402
import chat_completions as cc  # noqa: E402
from flask import Flask        # noqa: E402
from routes.chat_api import bp as chat_api_bp   # noqa: E402

CHAT_URL = "/v1/chat/completions"


def _expect(problems, cond, note):
    """断言收集：条件不满足时把说明追加进 problems，一次看全失败点。"""
    if not cond:
        problems.append(note)
    return problems


def _user(text):
    """构造一条标准 user 消息。"""
    return {"role": "user", "content": text}


def _tools_decl():
    """write_to_file 的标准 JSON Schema 声明（阶段 1b 前原样透传）。"""
    params = {
        "type": "object",
        "properties": {"path": {"type": "string"},
                       "content": {"type": "string"}},
        "required": ["path", "content"],
    }
    fn = {"name": "write_to_file",
          "description": "写文件（验收最小声明）",
          "parameters": params}
    return [{"type": "function", "function": fn}]


def _pick_message(resp):
    """取 choices[0].message；结构缺失时返回空 dict，让断言报出真实差异。"""
    try:
        return resp.get_json()["choices"][0]["message"]
    except Exception:
        return {}


def _enable_all_tools():
    """把全部内置工具置为启用，等价 create_app 后配置齐全的状态。"""
    cfg = dict(runtime.CONFIG or {})
    tools_cfg = cfg.get("tools") or {}
    for name in runtime.TOOLS:
        tools_cfg[name] = {"enabled": True}
    cfg["tools"] = tools_cfg
    runtime.CONFIG = cfg


def _setup_client():
    """装配最小应用（仅 chat 蓝图）并补齐运行时表，返回 test_client。

    为什么不用 create_app：完整装配会读本机真实配置与记忆库，工具启停
    随机器而变，验收结论不可复现。此处按 app._init_runtime 的口径补齐
    impl / TOOLS / DISPATCH / CONFIG 四张表（工具全启用）——chat 路由
    只依赖这四张表，行为与装配后的应用一致。
    """
    runtime.impl = tools_impl
    runtime.TOOLS = dict(tools_impl.TOOLS)
    runtime.DISPATCH = dict(tools_impl.DISPATCH)
    _enable_all_tools()
    app = Flask("check_chat_api")
    app.register_blueprint(chat_api_bp)
    app.config["TESTING"] = True
    return app.test_client()


def case_plain_chat(client, work):
    """场景 1：单轮纯文本对话 → 无调用意图，不执行任何工具。"""
    p = []
    r = client.post(CHAT_URL, json={
        "site_key": "acc-plain",
        "messages": [_user("你好，验收场景一：纯文本对话")],
    })
    _expect(p, r.status_code == 200, "HTTP %s" % r.status_code)
    msg = _pick_message(r)
    _expect(p, msg.get("role") == "assistant", "role=%r" % msg.get("role"))
    _expect(p, isinstance(msg.get("content"), str),
            "content 应为字符串（服务端不再代生成文本）")
    _expect(p, not msg.get("tool_calls"), "不应出现 tool_calls")
    return p


def case_tool_call(client, work):
    """场景 2：请求侧声明调用 → 服务端执行并回传 tool 结果与回声。"""
    p = []
    target = Path(work) / "scenario2.txt"
    args = json.dumps({"path": str(target), "content": "acc"}, ensure_ascii=False)
    r = client.post(CHAT_URL, json={
        "site_key": "acc-tool",
        "messages": [
            _user("帮我写文件"),
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call-acc-2", "type": "function",
                 "function": {"name": "write_to_file", "arguments": args}}]},
        ],
        "tools": _tools_decl(),
    })
    _expect(p, r.status_code == 200, "HTTP %s" % r.status_code)
    msg = _pick_message(r)
    calls = msg.get("tool_calls") or []
    _expect(p, len(calls) == 1, "回声 assistant 应含 1 个调用，实际 %d" % len(calls))
    tool_msgs = [m for m in (r.get_json(silent=True) or {}).get("messages") or []
                 if m.get("role") == "tool"]
    _expect(p, len(tool_msgs) == 1, "服务端应回传 1 条 tool 结果，实际 %d" % len(tool_msgs))
    written = target.is_file() and target.read_text(encoding="utf-8") == "acc"
    _expect(p, written, "服务端应已真实执行写入并落盘")
    return p


def case_tool_result_feedback(client, work):
    """场景 3：已回填结果的调用不重复执行，轮次正常收尾。"""
    p = []
    msgs = [
        _user("帮我查一下再写"),
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call-acc-3", "type": "function",
             "function": {"name": "write_to_file", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call-acc-3", "name": "write_to_file",
         "content": '{"success": true}'},
    ]
    r = client.post(CHAT_URL, json={
        "site_key": "acc-follow",
        "messages": msgs,
        "tools": _tools_decl(),
    })
    _expect(p, r.status_code == 200, "HTTP %s" % r.status_code)
    body = r.get_json(silent=True) or {}
    tool_msgs = [m for m in body.get("messages") or [] if m.get("role") == "tool"]
    _expect(p, len(tool_msgs) == 1, "已回填结果的调用不应再次执行，tool 消息实际 %d" % len(tool_msgs))
    msg = _pick_message(r)
    calls = msg.get("tool_calls") or []
    _expect(p, len(calls) == 1 and calls[0].get("id") == "call-acc-3",
            "回声应带出末条 assistant 的调用声明")
    return p


def case_multi_round(client, work):
    """场景 4：同一 site_key 连续请求，历史被正确累加。"""
    p = []
    first = client.post(CHAT_URL, json={
        "site_key": "acc-multi",
        "messages": [_user("第一问，验收多轮累加")],
    })
    _expect(p, first.status_code == 200, "首轮 HTTP %s" % first.status_code)
    n1 = len(first.get_json().get("messages") or [])
    second = client.post(CHAT_URL, json={
        "site_key": "acc-multi",
        "messages": [_user("第二问，验收多轮累加")],
    })
    _expect(p, second.status_code == 200, "次轮 HTTP %s" % second.status_code)
    hist = second.get_json().get("messages") or []
    _expect(p, len(hist) > n1, "历史未累加：%d -> %d" % (n1, len(hist)))
    _expect(p, hist[:n1] == (first.get_json().get("messages") or []),
            "旧历史应原样保留")
    return p


def case_stream_rejected(client, work):
    """场景 5：stream=true → 明确报错，绝不返回 200。"""
    p = []
    r = client.post(CHAT_URL, json={
        "site_key": "acc-stream",
        "messages": [_user("你好，验收流式拒绝")],
        "stream": True,
    })
    _expect(p, r.status_code != 200, "stream=true 不应返回 200")
    err = (r.get_json(silent=True) or {}).get("error")
    _expect(p, bool(err), "错误响应体缺失")
    return p


def case_tool_error_envelope(client, work):
    """场景 6：工具执行出错 → tool 消息 content 是含错误分类的 JSON 串。"""
    p = []
    r = client.post(CHAT_URL, json={
        "site_key": "acc-error",
        "messages": [
            _user("写文件"),
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call-acc-6", "type": "function",
                 "function": {"name": "write_to_file", "arguments": "{}"}}]},
        ],
        "tools": _tools_decl(),
    })
    _expect(p, r.status_code == 200, "工具失败不应变成 5xx：HTTP %s" % r.status_code)
    tool_msgs = [m for m in (r.get_json(silent=True) or {}).get("messages") or []
                 if m.get("role") == "tool"]
    _expect(p, len(tool_msgs) == 1, "tool 消息应恰好 1 条，实际 %d" % len(tool_msgs))
    body = {}
    if tool_msgs:
        raw = tool_msgs[0].get("content")
        _expect(p, isinstance(raw, str), "tool content 必须是字符串")
        try:
            body = json.loads(raw)
        except Exception:
            _expect(p, False, "tool content 不是合法 JSON：%r" % raw)
    _expect(p, body.get("success") is False, "success 应为 false")
    _expect(p, bool(body.get("errorType")), "缺少错误分类字段 errorType")
    return p


CASES = [
    ("单轮纯文本对话", case_plain_chat),
    ("单轮带一个工具调用", case_tool_call),
    ("工具结果回灌", case_tool_result_feedback),
    ("多轮延续", case_multi_round),
    ("stream 拒绝", case_stream_rejected),
    ("工具执行出错信封", case_tool_error_envelope),
]


def main():
    """逐场景执行并打印摘要；任何失败返回 1。"""
    failed = 0
    with tempfile.TemporaryDirectory() as work:
        # 会话落盘重定向到临时目录：验收过程不污染真实 data/chat_sessions
        cc._STORE_DIR = work
        client = _setup_client()
        for name, case in CASES:
            problems = case(client, work)
            if problems:
                failed += 1
                print("[FAIL] 场景：%s" % name)
                for note in problems:
                    print("       - %s" % note)
            else:
                print("[PASS] 场景：%s" % name)
    if failed:
        print("验收未通过：%d/%d 个场景失败" % (failed, len(CASES)))
        return 1
    print("验收通过：六类场景全部符合预期")
    return 0


if __name__ == "__main__":
    sys.exit(main())