"""标准会话历史存储测试（任务 A-3）。

覆盖任务书验收对应的单元级行为：
- merge_history 五种合并语义逐分支断言（验收 3）；
- 落盘前静默规范化：网页场景字段不进入历史，tool 消息只含标准
  字段且 content 为 JSON 字符串（验收 1、2）；
- 损坏文件兜底：备份保留 + 空历史重建，接口不中断（验收 5）；
- 同一 site_key 并发写不互踩、不交错（验收 5）；
- 两 site_key 互不串、重启（重载模块）后历史延续（验收 4）。
"""
import importlib
import json
import sys
import threading
from pathlib import Path

import pytest

# 导入路径自备（与 test_chat_api.py 同法）：conftest 只重定向状态，不做路径修正
_BASE = Path(__file__).resolve().parents[1]
for _entry in (str(_BASE), str(_BASE / "core")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import chat_completions as cc   # noqa: E402


@pytest.fixture()
def store_dir(tmp_path, monkeypatch):
    """会话存储重定向到临时目录；返回目录对象供直接检查落盘文件。"""
    d = tmp_path / "chat_sessions"
    monkeypatch.setattr(cc, "_STORE_DIR", str(d))
    return d


def _user(text):
    return {"role": "user", "content": text}


def _tool(call_id, name, content):
    return {"role": "tool", "tool_call_id": call_id, "name": name, "content": content}


# ---------- merge_history 五种合并语义（验收 3） ----------

def test_merge_empty_stored_rebuilds_by_incoming():
    incoming = [_user("你好"), {"role": "assistant", "content": "在"}]
    assert cc.merge_history([], incoming) == incoming


def test_merge_prefix_match_appends_new_tail():
    stored = [_user("一"), {"role": "assistant", "content": "答一"}]
    incoming = stored + [_user("二")]
    assert cc.merge_history(stored, incoming) == stored + [_user("二")]


def test_merge_true_prefix_is_idempotent():
    stored = [_user("一"), {"role": "assistant", "content": "答一"}, _user("二")]
    assert cc.merge_history(stored, stored[:2]) == stored


def test_merge_tail_repeat_not_duplicated():
    stored = [_user("一"), {"role": "assistant", "content": "答一"}]
    assert cc.merge_history(stored, [stored[-1]]) == stored


def test_merge_new_user_message_appends():
    stored = [_user("一"), {"role": "assistant", "content": "答一"}]
    assert cc.merge_history(stored, [_user("二")]) == stored + [_user("二")]


def test_merge_true_fork_rebuilds():
    # 真分叉（incoming 首条不是 user）：以 incoming 整体重建
    stored = [_user("一"), {"role": "assistant", "content": "答一"}]
    fork = [{"role": "assistant", "content": "另起炉灶"}]
    assert cc.merge_history(stored, fork) == fork


# ---------- 落盘前规范化：网页场景字段不进历史（验收 1、2） ----------

def test_web_fields_never_reach_disk(store_dir):
    msgs = [
        _user("看看"),
        # 网页场景字段混进 assistant 顶层与 tool_calls 内部
        {"role": "assistant", "content": None, "card_state": "running",
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "search", "arguments": "{}"},
                         "selector": ".btn", "card_status": "pending"}]},
    ]
    incoming = cc.normalize_messages(msgs)
    assert "card_state" not in incoming[1]   # 顶层附加字段已剔除
    cc.save_session("norm-web", incoming)
    disk = json.loads((store_dir / "norm-web.json").read_text(encoding="utf-8"))
    assert set(disk[1].keys()) == {"role", "content", "tool_calls"}
    tc = disk[1]["tool_calls"][0]
    assert set(tc.keys()) == {"id", "type", "function"}
    assert set(tc["function"].keys()) == {"name", "arguments"}


def test_tool_message_standard_fields_and_json_content(store_dir):
    msgs = [{"role": "tool", "tool_call_id": "c1", "name": "search",
             "content": "{\"success\": true}", "card_state": "done"}]
    incoming = cc.normalize_messages(msgs)
    assert set(incoming[0].keys()) == {"role", "content", "tool_call_id", "name"}
    cc.save_session("norm-tool", incoming)
    disk = json.loads((store_dir / "norm-tool.json").read_text(encoding="utf-8"))
    assert set(disk[0].keys()) == {"role", "content", "tool_call_id", "name"}
    # content 是 JSON 字符串，成败由其内 JSON 判断，无额外布尔字段
    assert json.loads(disk[0]["content"]) == {"success": True}


def test_non_dict_tool_call_entries_dropped():
    msgs = [{"role": "assistant", "content": None,
             "tool_calls": ["garbage",
                            {"id": "c2", "type": "function",
                             "function": {"name": "search", "arguments": "{}"}}]}]
    incoming = cc.normalize_messages(msgs)
    assert [tc["id"] for tc in incoming[0]["tool_calls"]] == ["c2"]


def test_web_fields_stripped_through_route(store_dir):
    # 接口级验证：带网页场景字段的 messages 进来，接口不报错、落盘干净
    from flask import Flask
    from routes.chat_api import bp
    app = Flask(__name__)
    app.register_blueprint(bp)
    app.config["TESTING"] = True
    client = app.test_client()
    msgs = [
        _user("你好"),
        {"role": "assistant", "content": None, "card_state": "running",
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "demo", "arguments": "{}"},
                         "selector": ".btn"}]},
        _tool("c1", "demo", "{\"success\": true}"),
    ]
    r = client.post("/v1/chat/completions",
                    json={"site_key": "route-web", "messages": msgs})
    assert r.status_code == 200
    disk = json.loads((store_dir / "route-web.json").read_text(encoding="utf-8"))
    assert set(disk[1].keys()) == {"role", "content", "tool_calls"}
    assert set(disk[1]["tool_calls"][0].keys()) == {"id", "type", "function"}


# ---------- 损坏文件兜底（验收 5） ----------

def test_corrupt_json_backed_up_and_history_rebuilds(store_dir):
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / "corrupt-1.json").write_text("{not json", encoding="utf-8")
    assert cc.load_session("corrupt-1") == []
    backup = store_dir / "corrupt-1.json.bad"
    assert backup.is_file(), "损坏文件应改名保留供诊断"
    assert backup.read_text(encoding="utf-8") == "{not json"
    # 备份后可正常重新累积，接口不中断
    cc.save_session("corrupt-1", [_user("重新开始")])
    assert len(cc.load_session("corrupt-1")) == 1


def test_non_list_file_backed_up(store_dir):
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / "corrupt-2.json").write_text("{\"a\": 1}", encoding="utf-8")
    assert cc.load_session("corrupt-2") == []
    assert (store_dir / "corrupt-2.json.bad").is_file()


# ---------- 并发写（验收 5） ----------

def test_concurrent_saves_keep_intact_history(store_dir):
    def worker(n):
        for i in range(20):
            cc.save_session("conc-1", [_user("w%d-%d" % (n, i))] * (i + 1))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    disk = json.loads((store_dir / "conc-1.json").read_text(encoding="utf-8"))
    # 最终内容必为某一次完整写入：等长同文序列，不交错、不撕裂
    assert all(m == disk[0] for m in disk)
    assert 1 <= len(disk) <= 20
    # 唯一临时文件都被 replace 收走，无残留
    assert not list(store_dir.glob("*.tmp"))


# ---------- site_key 隔离与重启延续（验收 4） ----------

def test_two_site_keys_isolated(store_dir):
    cc.save_session("iso-a", [_user("A 的问题")])
    cc.save_session("iso-b", [_user("B 的问题")])
    assert [m["content"] for m in cc.load_session("iso-a")] == ["A 的问题"]
    assert [m["content"] for m in cc.load_session("iso-b")] == ["B 的问题"]


def test_history_survives_module_reload(store_dir, monkeypatch):
    # 重启等价物：模块重载（_STORE_DIR 被模块体重置）后重新指向同一目录
    cc.save_session("reload-1",
                    [_user("第一问"), {"role": "assistant", "content": "答"}])
    fresh = importlib.reload(cc)
    monkeypatch.setattr(fresh, "_STORE_DIR", str(store_dir))
    history = fresh.load_session("reload-1")
    assert [m["content"] for m in history] == ["第一问", "答"]
