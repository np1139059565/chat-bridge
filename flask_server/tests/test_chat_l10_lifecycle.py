"""L10 钩子生命周期与请求间隔离测试（任务 A-10）：契约 22-27。

contract（1-17）与 edges（18-21）的续接。五条生命周期语义均先探针实测
后写死（探针记录见 docs/work-ai-a.md A-10 登记，跑完即删不进提交）：
- 契约 22：重复注册 fetcher 是叠加不是替换——两个钩子的回复按注册顺序
  逐个追加，两个 fetcher 每请求各触发一次；
- 契约 23：fetcher 违约（TypeError）或自身异常（RuntimeError）后钩子
  不被自动摘除，后续请求继续失败且不落盘；显式 clear 后注册表为空、
  后续请求回到无钩子基线；
- 契约 24：clear 幂等——注册两个钩子清一次即空，空表连清三次不抛、
  清理后注册表仍可正常复用；
- 契约 25：连续多请求间 fetcher 状态不泄漏——每请求恰好触发一次、
  fetcher 只见本 site_key 的合并历史（前请求内容不混入）、各会话
  独立落盘；
- 契约 26：注册快照——请求中途注册的钩子对当次请求触发零次，对下次
  请求正常生效（单次请求迭代用调用时点快照）；
- 契约 27：带 tool_calls 的分发轮 fetcher 恰好触发一次（工具执行与
  回环不再进钩子）。

样板沿 A-5/A-9 先例导入复用：夹具与常量来自 tests.test_chat_api，
钩子逐用例清理复用 contract 的 _clear_hooks（autouse）；sys.path
引导变量改名 _LIFE_ROOT 避开既有跨文件重复窗口。
"""
import sys
from pathlib import Path

_LIFE_ROOT = Path(__file__).resolve().parents[1]
if str(_LIFE_ROOT) not in sys.path:
    sys.path.insert(0, str(_LIFE_ROOT))

import json  # noqa: E402

import pytest  # noqa: E402

from tests.test_chat_api import (  # noqa: E402
    TOOLS_DECL,
    _init_runtime_tables,  # noqa: F401  autouse：write_to_file 进运行时工具表
    assistant_call,
    client,
    post,
    store_dir,
)
from tests.test_chat_l10_contract import _clear_hooks as hooks_clean  # noqa: E402,F401
import routes.chat_api as chat_api  # noqa: E402
import chat_completions as cc  # noqa: E402


# ---------- 契约 22：重复注册 fetcher 是叠加，各触发一次 ----------

def test_lifecycle_duplicate_registration_appends(client, store_dir):
    fires = {"first": 0, "second": 0}

    def fetch_first(history):
        fires["first"] += 1
        return "甲"

    def fetch_second(history):
        fires["second"] += 1
        return "乙"

    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(fetch_first))
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(fetch_second))
    r = post(client, {"site_key": "t-lc-dup", "messages": [{"role": "user", "content": "问"}]})
    assert r.status_code == 200
    assert [m["content"] for m in r.get_json()["messages"]] == ["问", "甲", "乙"], "重复注册为叠加"
    assert fires == {"first": 1, "second": 1}, "两个 fetcher 每请求各触发一次"

# ---------- 契约 22：重复注册 fetcher 是叠加，各触发一次 ----------

def test_lifecycle_duplicate_registration_appends(client, store_dir):
    fires = {"first": 0, "second": 0}

    def fetch_first(history):
        fires["first"] += 1
        return "甲"

    def fetch_second(history):
        fires["second"] += 1
        return "乙"

    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(fetch_first))
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(fetch_second))
    r = post(client, {"site_key": "t-lc-dup", "messages": [{"role": "user", "content": "问"}]})
    assert r.status_code == 200
    assert [m["content"] for m in r.get_json()["messages"]] == ["问", "甲", "乙"], \
        "重复注册为叠加：回复按注册顺序逐个追加（实测语义写死）"
    assert fires == {"first": 1, "second": 1}, "两个 fetcher 每请求各触发一次"


# ---------- 契约 23：违约/异常不自动摘除，显式清理后无残留 ----------

def test_lifecycle_violation_and_exception_keep_hooks(client, store_dir):
    # 与 edges 契约 21 互补：那边盯恢复闭环，这边盯注册表与落盘两条不变量
    bad_key = "t-lc-bad"
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(lambda h: 42))
    with pytest.raises(TypeError):
        post(client, {"site_key": bad_key, "messages": [{"role": "user", "content": "x"}]})
    assert len(chat_api._PRE_DISPATCH_HOOKS) == 1, "违约后钩子仍留在注册表（实测写死）"
    assert not (store_dir / (bad_key + ".json")).is_file(), "违约请求不落盘"

    def broken_fetcher(history):
        raise RuntimeError("lifecycle-fetcher-failure")

    chat_api.clear_pre_dispatch_hooks()
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(broken_fetcher))
    with pytest.raises(RuntimeError, match="lifecycle-fetcher-failure"):
        post(client, {"site_key": bad_key, "messages": [{"role": "user", "content": "y"}]})
    assert len(chat_api._PRE_DISPATCH_HOOKS) == 1, "异常后钩子同样不被自动摘除"
    assert not (store_dir / (bad_key + ".json")).is_file(), "异常请求不落盘"

    chat_api.clear_pre_dispatch_hooks()
    assert chat_api._PRE_DISPATCH_HOOKS == [], "显式清理后注册表为空、无残留"
    r = post(client, {"site_key": bad_key, "messages": [{"role": "user", "content": "好"}]})
    assert r.status_code == 200
    assert r.get_json()["messages"] == [{"role": "user", "content": "好"}], \
        "清理后请求回到无钩子基线：不代生成 assistant"


# ---------- 契约 24：clear 幂等，清理后注册表仍可复用 ----------

def test_lifecycle_clear_idempotent(client, store_dir):
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(lambda h: "一号"))
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(lambda h: "二号"))
    assert len(chat_api._PRE_DISPATCH_HOOKS) == 2, "注册两个钩子"
    chat_api.clear_pre_dispatch_hooks()
    for _ in range(3):
        chat_api.clear_pre_dispatch_hooks()  # 空表连清不抛（幂等）
    assert chat_api._PRE_DISPATCH_HOOKS == [], "多次 clear 后仍为空"
    r = post(client, {"site_key": "t-lc-idem", "messages": [{"role": "user", "content": "问"}]})
    assert r.status_code == 200
    assert r.get_json()["messages"] == [{"role": "user", "content": "问"}], "清理后走无钩子基线"
    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(lambda h: "复用"))
    r = post(client, {"site_key": "t-lc-idem", "messages": [{"role": "user", "content": "再问"}]})
    assert [m["content"] for m in r.get_json()["messages"]] == ["问", "再问", "复用"], \
        "clear 不破坏注册表的后续复用"


# ---------- 契约 25：多请求间 fetcher 状态隔离，每请求触发一次 ----------

def test_lifecycle_fetcher_state_isolated_across_requests(client, store_dir):
    fires = []
    seen = []

    def fetch(history):
        fires.append(1)
        seen.append([m.get("content") for m in history])
        return "答%d" % len(fires)

    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(fetch))
    keys = ["t-lc-s1", "t-lc-s2", "t-lc-s3"]
    for i, key in enumerate(keys):
        r = post(client, {"site_key": key, "messages": [{"role": "user", "content": "问%d" % i}]})
        assert r.status_code == 200
    assert len(fires) == 3, "三个请求合计恰好触发三次"
    assert seen == [["问0"], ["问1"], ["问2"]], \
        "fetcher 只见本 site_key 合并历史，前请求不混入（无跨请求泄漏）"
    for i, key in enumerate(keys):
        stored = json.loads((store_dir / ("%s.json" % key)).read_text(encoding="utf-8"))
        assert [m["content"] for m in stored] == ["问%d" % i, "答%d" % (i + 1)], "各会话独立落盘"

# ---------- 契约 26：注册快照——中途注册当次零次、下次生效 ----------

def test_lifecycle_registration_snapshot(client, store_dir):
    late_fires = []
    registered = {"done": False}

    def late_fetch(history):
        late_fires.append(1)
        return "迟到"

    def outer(history):
        if not registered["done"]:
            registered["done"] = True
            chat_api.register_pre_dispatch_hook(cc.model_reply_hook(late_fetch))
        return "先到"

    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(outer))
    r = post(client, {"site_key": "t-lc-snap", "messages": [{"role": "user", "content": "问"}]})
    assert r.status_code == 200
    assert [m["content"] for m in r.get_json()["messages"]] == ["问", "先到"], \
        "请求中途注册的钩子对当次触发零次（快照语义，实测写死）"
    assert late_fires == [], "中途注册的 fetcher 当次未被触发"
    r = post(client, {"site_key": "t-lc-snap2", "messages": [{"role": "user", "content": "再问"}]})
    assert [m["content"] for m in r.get_json()["messages"]] == ["再问", "先到", "迟到"], \
        "下次请求两个钩子都正常生效"
    assert late_fires == [1], "新钩子对后续请求每请求一次"


# ---------- 契约 27：带 tool_calls 的分发轮 fetcher 恰好触发一次 ----------

def test_lifecycle_dispatch_round_fires_once(client, store_dir, tmp_path):
    fires = []
    target = tmp_path / "once.txt"

    def fetch(history):
        fires.append(1)
        return assistant_call("call_lc", "write_to_file",
                               json.dumps({"path": target.as_posix(), "content": "x"}))

    chat_api.register_pre_dispatch_hook(cc.model_reply_hook(fetch))
    r = post(client, {"site_key": "t-lc-disp", "messages": [{"role": "user", "content": "写"}],
                      "tools": TOOLS_DECL})
    assert r.status_code == 200
    assert len(fires) == 1, "带 tool_calls 的分发轮 fetcher 恰好触发一次"
    assert target.read_text(encoding="utf-8") == "x", "声明的调用已真实执行"
    assert r.get_json()["choices"][0]["finish_reason"] == "tool_calls", "分发轮按标准收口"