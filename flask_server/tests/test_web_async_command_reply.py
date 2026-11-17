"""网页版异步指令下发应有即时可见回执。

回归：/sp、/sessions 等指令经 _dispatch_with_result 下发后，结果依赖浏览器
回传；抽屉不在线时用户看不到任何反馈（2026-11-12 图 10）。
"""
import os
import sys
import types
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from remote_bridge import command_dispatch as cd  # noqa: E402


class _FakeBus:
    def create(self, **kw):
        return types.SimpleNamespace(id="0" * 32)


def _install_fake_dq(monkeypatch):
    fake = types.ModuleType("delivery_queue")
    fake.command_bus = _FakeBus()
    monkeypatch.setitem(sys.modules, "delivery_queue", fake)


def test_web_async_command_has_immediate_reply(monkeypatch):
    _install_fake_dq(monkeypatch)
    got = []
    cd.set_web_reply_sink(lambda t: got.append(t))
    cd._dispatch_with_result("screenshot", {}, cd.WEB_OPENID)
    assert len(got) == 1 and "等待页面响应" in got[0]


def test_other_channels_get_no_web_reply(monkeypatch):
    _install_fake_dq(monkeypatch)
    got = []
    cd.set_web_reply_sink(lambda t: got.append(t))
    cd._dispatch_with_result("screenshot", {}, "qq-user-123")
    assert got == []


if __name__ == "__main__":
    class _MP:
        def setitem(self, d, k, v):
            d[k] = v
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn(_MP())
    print("OK: all tests passed")