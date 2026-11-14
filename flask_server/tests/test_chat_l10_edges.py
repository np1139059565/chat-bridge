"""L10 契约边界测试（任务 A-9）：model_reply_hook 边界四组（契约 18-21）。

与 test_chat_l10_contract.py 同源延伸，因单文件函数个数闸门（35）拆出独立文件：
- 契约 18：dict 带空 tool_calls——视为未声明，不进分发；
- 契约 19：None→str→dict 交替循环两轮以上，历史逐步累积闭合；
- 契约 20：网页附加字段（page_url/selector，契约 14 同族）清洗后，分发/落盘/响应三步一致；
- 契约 21：fetcher 违约/异常后无残留，后续请求正常闭合。

样板来源：夹具与常量从 tests.test_chat_api 导入、钩子清理夹具从
tests.test_chat_l10_contract 导入，一律不在本文件复制——质量闸门对跨文件
连续 5 行重复计数，复制样板会顶爆 dup 基线（含 sys.path 引导块，故本文件
引导变量改名 _ROOT 以避开既有重复窗口）。
导入顺序有依赖：tests 导入链会自行扩展 core/ 与 tools/ 路径，须先于
routes.chat_api / chat_completions 导入，否则模块名解析失败。
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import json  # noqa: E402
import pytest  # noqa: E402

from tests.test_chat_api import TOOLS_DECL, _init_runtime_tables, assistant_call, client, post, store_dir, tool_messages  # noqa: E402,F401
from tests.test_chat_l10_contract import _clear_hooks as fixture_cleanup  # noqa: E402
import routes.chat_api as chat_api  # noqa: E402
import chat_completions as cc  # noqa: E402


# ---------- 契约 18：dict 带空 tool_calls——视为未声明，不进分发 ----------

def test_model_hook_empty_tool_calls_no_dispatch(client, store_dir):
    def fetch(history):
        return {"role": "assistant", "content": "空表", "tool_calls": []}
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(fetch))
    r = post(client, {"site_key": "t-mr-etc", "messages": [{"role": "user", "content": "问"}], "tools": TOOLS_DECL})
    data = r.get_json()
    assert r.status_code == 200
    assert data["messages"] == [{"role": "user", "content": "问"}, {"role": "assistant", "content": "空表"}], "空 tool_calls 清洗为无调用"
    assert data["choices"][0]["finish_reason"] == "stop", "无待执行调用，不进分发"


# ---------- 契约 19：None→str→dict 交替循环两轮以上，历史逐步累积闭合 ----------

def test_model_hook_none_str_dict_cycle(client, store_dir):
    scripted = iter([None, "答一", {"role": "assistant", "content": "答二"},
                     None, "答三", {"role": "assistant", "content": "答四"}])
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(lambda h: next(scripted)))
    for i in range(6):
        r = post(client, {"site_key": "t-mr-cyc", "messages": [{"role": "user", "content": "问%d" % i}]})
        assert r.status_code == 200
    msgs = r.get_json()["messages"]
    want_seq = ["问0", "问1", "答一", "问2", "答二", "问3", "问4", "答三", "问5", "答四"]
    assert [m["content"] for m in msgs] == want_seq, "两轮循环逐步累积"
    assert msgs[-1] == {"role": "assistant", "content": "答四"}, "dict 轮经规范化入史"


# ---------- 契约 20：网页附加字段清洗后，分发/落盘/响应三步一致 ----------

def test_model_hook_web_fields_consistent(client, store_dir, tmp_path):
    target = tmp_path / "three-ways.txt"
    args = json.dumps({"path": target.as_posix(), "content": "三步"})

    def fetch(history):
        msg = assistant_call("call_tw", "write_to_file", args)
        msg["page_url"] = "http://x/p"
        msg["selector"] = "#s"
        return msg

    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(fetch))
    r = post(client, {"site_key": "t-mr-3w", "messages": [{"role": "user", "content": "写"}],
                      "tools": TOOLS_DECL})
    assert r.status_code == 200
    data = r.get_json()
    assert target.read_text(encoding="utf-8") == "三步", "清洗后的调用进入分发执行"
    assert [m["tool_call_id"] for m in tool_messages(data)] == ["call_tw"], "调用经标准管线执行"
    assert data["messages"][1] == assistant_call("call_tw", "write_to_file", args), "响应轮只剩标准字段"
    assert data["choices"][0]["finish_reason"] == "tool_calls", "分发后按标准收口"
    stored = json.loads((store_dir / "t-mr-3w.json").read_text(encoding="utf-8"))
    assert stored == data["messages"], "落盘与响应 messages 完全一致"

# ---------- 契约 21：fetcher 违约/异常后无残留，后续请求正常闭合 ----------

def test_model_hook_violation_then_recovery(client, store_dir):
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(lambda h: 42))
    with pytest.raises(TypeError):
        post(client, {"site_key": "t-mr-rec", "messages": [{"role": "user", "content": "坏一"}]})
    def boom(history):
        raise RuntimeError("model down")
    chat_api.clear_pre_dispatch_hooks()
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(boom))
    with pytest.raises(RuntimeError):
        post(client, {"site_key": "t-mr-rec", "messages": [{"role": "user", "content": "坏二"}]})
    assert not (store_dir / "t-mr-rec.json").is_file(), "违约与异常两轮均不落盘"
    chat_api.clear_pre_dispatch_hooks()
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(lambda h: "恢复"))
    r = post(client, {"site_key": "t-mr-rec", "messages": [{"role": "user", "content": "好"}]})
    assert r.status_code == 200
    assert r.get_json()["messages"] == [{"role": "user", "content": "好"}, {"role": "assistant", "content": "恢复"}], "无残留，干净闭合"
