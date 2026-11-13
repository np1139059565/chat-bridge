"""L10 契约入口测试（任务 A-5）：register_pre_dispatch_hook 行为契约。

入口定义在 routes/chat_api.py（标准链路 POST /v1/chat/completions 的工具
分发前可插拔钩子），固定点位：历史合并之后、_execute_pending 之前。

契约要点（与 register_pre_dispatch_hook docstring 一致）：
- 钩子收到合并后的完整 history（list[dict]），视为只读入参；
- 返回 None：沿用原 history；返回 list：整体替换后续各步使用的 history
  （分发输入、落盘、响应 messages）；
- 多钩子按注册顺序链式执行，前一钩子的产出是下一钩子的入参；
- 返回非 None/list 是契约违约，抛 TypeError；
- 钩子内部异常不被入口捕获：请求失败且无部分副作用（不执行工具、不落盘）；
- 注册表是进程级状态，用例之间不得泄漏（夹具前后清空）。

A-7 追加（契约 9-17）：cc.model_reply_hook(fetch) 把「history 送真实模型」
包装为可注册钩子。fetcher 返回 None（不代签）/ str（assistant 文本）/
dict（assistant 轮，可带 tool_calls）；回复经规范化追加，分发、落盘、
回声同步生效；违约抛 TypeError、异常上抛且无部分副作用。

样板来源：夹具（store_dir / client / _init_runtime_tables）、常量与辅助
函数一律从 tests.test_chat_api 导入复用，不在本文件复制——质量闸门对
跨文件连续 5 行重复计数，复制样板会顶爆 dup 基线（本文件初版曾因此
触发结构质量钩子，改为导入复用后归零）。
"""
import sys
from pathlib import Path

# 先保证 flask_server 根可导入（tests 是包、有 __init__.py）：夹具与样板
# 一律从 tests.test_chat_api 导入复用；该模块顶层还会自行补 core/ 与
# tools/ 两条路径，随后 import routes.chat_api 才能解析。
_BASE = Path(__file__).resolve().parents[1]
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

import json  # noqa: E402

import pytest  # noqa: E402

from tests.test_chat_api import (  # noqa: E402
    TOOLS_DECL,
    _init_runtime_tables,
    assistant_call,
    client,
    post,
    store_dir,
    tool_messages,
)
import routes.chat_api as chat_api  # noqa: E402
import chat_completions as cc  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_hooks():
    """用例前后清空钩子注册表：L10 入口是进程级状态，必须逐用例隔离。"""
    chat_api.clear_pre_dispatch_hooks()
    yield
    chat_api.clear_pre_dispatch_hooks()


# ---------- 契约 1：钩子收到合并后的 history（只读），请求不受影响 ----------

def test_hook_receives_merged_history(client, store_dir):
    seen = []

    def spy(history):
        seen.append(list(history))
        return None

    chat_api.register_pre_dispatch_hook(spy)
    r = post(client, {"site_key": "t-l10-1", "messages": [{"role": "user", "content": "第一问"}]})
    assert r.status_code == 200
    assert seen, "钩子应被调用"
    assert seen[0] == [{"role": "user", "content": "第一问"}]
    data = r.get_json()
    assert data["messages"] == [{"role": "user", "content": "第一问"}], "返回 None 时链路行为不变"
    assert data["choices"][0]["finish_reason"] == "stop"


def test_hook_sees_accumulated_history_on_second_round(client, store_dir):
    post(client, {"site_key": "t-l10-acc", "messages": [{"role": "user", "content": "第一问"}]})
    captured = []

    def spy(history):
        captured.append([dict(m) for m in history])
        return None

    chat_api.register_pre_dispatch_hook(spy)
    r = post(client, {"site_key": "t-l10-acc", "messages": [{"role": "user", "content": "第二问"}]})
    assert r.status_code == 200
    assert [m["content"] for m in captured[0]] == ["第一问", "第二问"], "钩子收到的是合并累积后的历史"


# ---------- 契约 2：返回 list 替换后续各步使用的 history ----------

def test_hook_return_replaces_history_and_persists(client, store_dir):
    def inject(history):
        return history + [{"role": "system", "content": "L10 注入"}]

    chat_api.register_pre_dispatch_hook(inject)
    r = post(client, {"site_key": "t-l10-2", "messages": [{"role": "user", "content": "你好"}]})
    assert r.status_code == 200
    data = r.get_json()
    assert data["messages"] == [
        {"role": "user", "content": "你好"},
        {"role": "system", "content": "L10 注入"},
    ]
    stored = json.loads((store_dir / "t-l10-2.json").read_text(encoding="utf-8"))
    assert stored == data["messages"], "替换后的 history 同步落盘"


# ---------- 契约 3：多钩子按注册顺序链式执行 ----------

def test_hooks_chain_in_registration_order(client, store_dir):
    calls = []

    def first(history):
        calls.append("first")
        return history + [{"role": "system", "content": "a"}]

    def second(history):
        calls.append("second")
        assert history[-1]["content"] == "a", "后一钩子收到前一钩子的产出"
        return history + [{"role": "system", "content": "b"}]

    chat_api.register_pre_dispatch_hook(first)
    chat_api.register_pre_dispatch_hook(second)
    r = post(client, {"site_key": "t-l10-3", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert calls == ["first", "second"]
    assert [m["content"] for m in r.get_json()["messages"][1:]] == ["a", "b"]


# ---------- 契约 4：钩子每请求执行一次，与待执行调用数无关 ----------

def test_hook_runs_once_per_request(client, store_dir, tmp_path):
    t1 = tmp_path / "h1.txt"
    t2 = tmp_path / "h2.txt"
    calls = []

    def once(history):
        calls.append(1)
        return None

    chat_api.register_pre_dispatch_hook(once)
    msgs = [
        {"role": "user", "content": "写两个文件"},
        assistant_call(
            "c1", "write_to_file",
            json.dumps({"path": t1.as_posix(), "content": "1"}),
        ),
    ]
    msgs[-1]["tool_calls"].append(
        {"id": "c2", "type": "function",
         "function": {"name": "write_to_file",
                      "arguments": json.dumps({"path": t2.as_posix(), "content": "2"})}}
    )
    r = post(client, {"site_key": "t-l10-7", "messages": msgs, "tools": TOOLS_DECL})
    assert r.status_code == 200
    assert [m["tool_call_id"] for m in tool_messages(r.get_json())] == ["c1", "c2"], "工具仍逐个执行"
    assert len(calls) == 1, "钩子每请求只执行一次"


# ---------- 契约 5：钩子产出即分发输入（注入的调用会被执行） ----------

def test_hook_output_feeds_dispatch(client, store_dir, tmp_path):
    target = tmp_path / "injected.txt"

    def inject_call(history):
        return history + [
            assistant_call(
                "call_inj", "write_to_file",
                json.dumps({"path": target.as_posix(), "content": "from hook"}),
            ),
        ]

    chat_api.register_pre_dispatch_hook(inject_call)
    r = post(client, {"site_key": "t-l10-9", "messages": [{"role": "user", "content": "普通请求"}]})
    assert r.status_code == 200
    data = r.get_json()
    tms = tool_messages(data)
    assert [m["tool_call_id"] for m in tms] == ["call_inj"], "注入的调用进入分发并被执行"
    assert target.read_text(encoding="utf-8") == "from hook"
    assert data["choices"][0]["finish_reason"] == "tool_calls"


# ---------- 契约 6：钩子异常不被吞——请求失败且无部分副作用 ----------

def test_hook_error_fails_request_without_partial_effects(client, store_dir, tmp_path):
    target = tmp_path / "never.txt"

    def boom(history):
        raise RuntimeError("hook boom")

    chat_api.register_pre_dispatch_hook(boom)
    with pytest.raises(RuntimeError, match="hook boom"):
        post(
            client,
            {
                "site_key": "t-l10-4",
                "messages": [
                    {"role": "user", "content": "写文件"},
                    assistant_call(
                        "call_l10e", "write_to_file",
                        json.dumps({"path": target.as_posix(), "content": "x"}),
                    ),
                ],
                "tools": TOOLS_DECL,
            },
        )
    assert not target.exists(), "钩子失败时工具不得已执行"
    assert not (store_dir / "t-l10-4.json").is_file(), "钩子失败时历史不得已落盘"


# ---------- 契约 7：返回非 None/list 是契约违约（TypeError） ----------

def test_hook_returning_non_list_breaks_contract(client, store_dir):
    def bad_hook(history):
        return {"role": "system", "content": "x"}

    chat_api.register_pre_dispatch_hook(bad_hook)
    with pytest.raises(TypeError):
        post(client, {"site_key": "t-l10-5", "messages": [{"role": "user", "content": "hi"}]})
    assert not (store_dir / "t-l10-5.json").is_file(), "违约请求同样不得落盘"


# ---------- 契约 8：用例之间钩子不泄漏 ----------

def test_hooks_do_not_leak_between_requests(client, store_dir):
    def leak(history):
        return history + [{"role": "system", "content": "leaked"}]

    chat_api.register_pre_dispatch_hook(leak)
    r1 = post(client, {"site_key": "t-l10-6a", "messages": [{"role": "user", "content": "r1"}]})
    assert r1.status_code == 200
    assert len(r1.get_json()["messages"]) == 2

    chat_api.clear_pre_dispatch_hooks()
    r2 = post(client, {"site_key": "t-l10-6b", "messages": [{"role": "user", "content": "r2"}]})
    assert r2.status_code == 200
    assert r2.get_json()["messages"] == [{"role": "user", "content": "r2"}], "清空后钩子不再生效"

# ---------- A-7 契约 9：model_reply_hook——fetcher 返回 None 不代签 ----------

def test_model_hook_none_keeps_chain_untouched(client, store_dir):
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(lambda h: None))
    r = post(client, {"site_key": "t-mr-none", "messages": [{"role": "user", "content": "你好"}]})
    assert r.status_code == 200
    data = r.get_json()
    assert data["messages"] == [{"role": "user", "content": "你好"}], "None 不代签：链路行为与现状一致"
    assert data["choices"][0]["message"]["content"] == ""
    assert data["choices"][0]["finish_reason"] == "stop"


# ---------- A-7 契约 10：str 回复追加为 assistant 轮，回声 / 落盘同步 ----------

def test_model_hook_str_reply_appends_assistant(client, store_dir):
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(lambda h: "模型回答"))
    r = post(client, {"site_key": "t-mr-str", "messages": [{"role": "user", "content": "问"}]})
    assert r.status_code == 200
    data = r.get_json()
    assert data["messages"] == [
        {"role": "user", "content": "问"},
        {"role": "assistant", "content": "模型回答"},
    ]
    assert data["choices"][0]["message"]["content"] == "模型回答", "回声取末条 assistant 即模型回复"
    assert data["choices"][0]["finish_reason"] == "stop"
    stored = json.loads((store_dir / "t-mr-str.json").read_text(encoding="utf-8"))
    assert stored == data["messages"], "模型回复同步落盘"


# ---------- A-7 契约 11：fetcher 收到的是合并后累积历史 ----------

def test_model_hook_fetcher_sees_merged_history(client, store_dir):
    post(client, {"site_key": "t-mr-see", "messages": [{"role": "user", "content": "第一问"}]})
    captured = []

    def fetch(history):
        captured.append([dict(m) for m in history])
        return None

    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(fetch))
    r = post(client, {"site_key": "t-mr-see", "messages": [{"role": "user", "content": "第二问"}]})
    assert r.status_code == 200
    assert [m["content"] for m in captured[0]] == ["第一问", "第二问"], "fetcher 入参是合并后的完整历史"


# ---------- A-7 契约 12：dict 回复带 tool_calls——模型声明意图，服务端执行 ----------

def test_model_hook_dict_with_tool_calls_dispatches(client, store_dir, tmp_path):
    target = tmp_path / "by_model.txt"

    def fetch(history):
        return assistant_call(
            "call_m1", "write_to_file",
            json.dumps({"path": target.as_posix(), "content": "from model"}),
        )

    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(fetch))
    r = post(client, {"site_key": "t-mr-tc", "messages": [{"role": "user", "content": "写文件"}],
                      "tools": TOOLS_DECL})
    assert r.status_code == 200
    data = r.get_json()
    tms = tool_messages(data)
    assert [m["tool_call_id"] for m in tms] == ["call_m1"], "模型声明的调用进入标准执行管线"
    assert target.read_text(encoding="utf-8") == "from model", "调用被真实执行"
    assert data["choices"][0]["finish_reason"] == "tool_calls"


# ---------- A-7 契约 13：多轮循环闭合（模型回复落盘后可续轮） ----------

def test_model_hook_two_round_loop_closes(client, store_dir):
    replies = iter(["第一答", "第二答"])
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(lambda h: next(replies)))
    r1 = post(client, {"site_key": "t-mr-loop", "messages": [{"role": "user", "content": "一"}]})
    r2 = post(client, {"site_key": "t-mr-loop", "messages": [{"role": "user", "content": "二"}]})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.get_json()["messages"] == [
        {"role": "user", "content": "一"},
        {"role": "assistant", "content": "第一答"},
        {"role": "user", "content": "二"},
        {"role": "assistant", "content": "第二答"},
    ], "模型回复落盘续轮，第二轮 fetcher 见累积历史"


# ---------- A-7 契约 14：dict 回复的网页附加字段被规范化清洗 ----------

def test_model_hook_dict_reply_sanitized(client, store_dir):
    def fetch(history):
        return {"role": "assistant", "content": "回",
                "page_url": "http://x" , "selector": "#a"}

    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(fetch))
    r = post(client, {"site_key": "t-mr-san", "messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 200
    assert r.get_json()["messages"][-1] == {"role": "assistant", "content": "回"}, "附加字段被清洗"


# ---------- A-7 契约 15：fetcher 返回非法类型 → TypeError，无副作用 ----------

def test_model_hook_bad_return_type_fails_cleanly(client, store_dir):
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(lambda h: 42))
    with pytest.raises(TypeError):
        post(client, {"site_key": "t-mr-bad", "messages": [{"role": "user", "content": "x"}]})
    assert not (store_dir / "t-mr-bad.json").is_file(), "违约请求不得落盘"


# ---------- A-7 契约 16：dict 回复 role 非 assistant → TypeError ----------

def test_model_hook_dict_requires_assistant_role(client, store_dir):
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(
        lambda h: {"role": "user", "content": "x"}))
    with pytest.raises(TypeError):
        post(client, {"site_key": "t-mr-role", "messages": [{"role": "user", "content": "x"}]})
    assert not (store_dir / "t-mr-role.json").is_file()


# ---------- A-7 契约 17：fetcher 异常原样上抛，无部分副作用 ----------

def test_model_hook_fetcher_error_propagates(client, store_dir, tmp_path):
    target = tmp_path / "never-mr.txt"

    def fetch(history):
        raise RuntimeError("model down")

    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(fetch))
    with pytest.raises(RuntimeError, match="model down"):
        post(client, {"site_key": "t-mr-err", "messages": [
            {"role": "user", "content": "写"},
            assistant_call("call_merr", "write_to_file",
                           json.dumps({"path": target.as_posix(), "content": "x"})),
        ], "tools": TOOLS_DECL})
    assert not target.exists(), "fetcher 失败时工具不得已执行"
    assert not (store_dir / "t-mr-err.json").is_file(), "fetcher 失败时历史不得已落盘"
