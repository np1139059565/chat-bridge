"""网页版异步指令超时终态提示。

回归：/sp 等指令下发后抽屉离线，request_id 在 PENDING_TTL 后静默过期，
用户只看到「等待页面响应」却等不到任何终态（2026-11-12）。
"""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from remote_bridge import command_dispatch as cd  # noqa: E402


def _sink():
    got = []
    cd.set_web_reply_sink(lambda t: got.append(t))
    return got


def test_expired_web_request_gets_timeout_reply():
    got = _sink()
    rid = "r-timeout"
    with cd._pending_lock:
        cd._pending[rid] = {"openid": cd.WEB_OPENID,
                            "expire": time.time() - 1,
                            "action": "screenshot"}
    assert cd._expire_pending_one(rid) is True
    assert len(got) == 1 and "超时" in got[0] and "screenshot" in got[0]
    assert rid not in cd._pending


def test_completed_request_gets_no_timeout_reply():
    got = _sink()
    rid = "r-done"
    with cd._pending_lock:
        cd._pending[rid] = {"openid": cd.WEB_OPENID,
                            "expire": time.time() + 60,
                            "action": "screenshot"}
    assert cd.take_pending(rid) is not None   # 模拟结果已正常回传
    assert cd._expire_pending_one(rid) is False
    assert got == []


def test_non_web_timeout_is_silent():
    got = _sink()
    rid = "r-qq"
    with cd._pending_lock:
        cd._pending[rid] = {"openid": "qq-user", "expire": time.time() - 1,
                            "action": "screenshot"}
    assert cd._expire_pending_one(rid) is True
    assert got == []


def test_timer_is_scheduled_for_web_async_command():
    src = open(cd.__file__, encoding="utf-8").read()
    assert "_start_async_timeout_watch(rid)" in src
    assert "threading.Timer(" in src


def test_register_pending_cleans_expired_with_notice():
    got = _sink()
    stale = "r-stale"
    with cd._pending_lock:
        cd._pending[stale] = {"openid": cd.WEB_OPENID,
                              "expire": time.time() - 1,
                              "action": "list_sessions"}
    new_rid = cd._register_pending(cd.WEB_OPENID, "screenshot")
    assert stale not in cd._pending
    assert len(got) == 1 and "list_sessions" in got[0]
    with cd._pending_lock:
        assert cd._pending[new_rid]["action"] == "screenshot"
        cd._pending.pop(new_rid, None)


if __name__ == "__main__":
    for _n, _f in sorted(globals().items()):
        if _n.startswith("test_") and callable(_f):
            _f()
    print("OK: all tests passed")