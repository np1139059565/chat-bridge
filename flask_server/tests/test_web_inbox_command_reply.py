"""指令回执（command-reply）与 /sp 结果（command-image）跨站点可见。

回归：网页版敲 /h 后「我」气泡在、系统回执却不见（2026-11-12）。
根因：回执写入未带 site_key，前端按站点拉取时被 _filter_site 过滤。
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from web_bridge import web_inbox  # noqa: E402


def _m(role, kind, site=""):
    return {"role": role, "kind": kind, "site_key": site, "seq": 1, "text": "x"}


def test_command_reply_visible_in_any_site():
    msgs = [
        _m("user", "command", "glm"),
        _m("system", "command-reply", ""),
        _m("user", "web-user", "glm"),
        _m("ai", "", "other"),
    ]
    out = web_inbox._filter_site(msgs, "glm")
    assert any(m["kind"] == "command-reply" for m in out)
    assert any(m["kind"] == "web-user" for m in out)
    assert not any(m.get("site_key") == "other" for m in out)


def test_command_reply_visible_when_no_site():
    msgs = [_m("system", "command-reply", ""), _m("ai", "", "glm")]
    out = web_inbox._filter_site(msgs, "")
    assert any(m["kind"] == "command-reply" for m in out)
    assert not any(m.get("site_key") == "glm" for m in out)


def test_none_site_keeps_all():
    msgs = [_m("ai", "", "glm"), _m("system", "command-reply", "")]
    assert web_inbox._filter_site(msgs, None) is msgs


def test_command_image_visible_in_any_site():
    """ /sp 截图结果同样不该被站点过滤吞掉。 """
    msgs = [_m("user", "command", "glm"),
            _m("system", "command-image", ""),
            _m("ai", "", "other")]
    out = web_inbox._filter_site(msgs, "glm")
    assert any(m["kind"] == "command-image" for m in out)
    assert not any(m.get("site_key") == "other" for m in out)


def test_command_bubble_still_scoped():
    """ 用户发出的指令气泡仍按站点隔离，不能被全局放行带过来。 """
    msgs = [_m("user", "command", "glm"), _m("user", "command", "other")]
    out = web_inbox._filter_site(msgs, "glm")
    assert len(out) == 1 and out[0]["site_key"] == "glm"


if __name__ == "__main__":
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
    print("OK: all tests passed")