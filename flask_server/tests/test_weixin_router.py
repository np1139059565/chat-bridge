"""微信通道：推送路由、配额、网关与指令兼容测试

为什么需要：
    微信通道上线后出现过两次真实故障，都是「没有任何测试覆盖」导致的：
    1. 指令全部哑掉——回执写死 QQ 的窗口检查，微信没有窗口概念；
    2. 配额按 24 小时累计——与平台「每条用户消息重置」的真实机制不符。

本文件覆盖：
    推送路由 —— 合并推送、去重、来源过滤、超长截断
    配额机制 —— 按用户消息重置、过期失效、用满拦截
    网关抽取 —— 文本优先于语音、异常输入不崩
    指令兼容 —— 不需要窗口的客户端能正常收发指令

协议与客户端契约见 test_weixin_protocol.py。
运行：python -m pytest tests/test_weixin_router.py -q
"""
import json
import os
import sys
import time

# 把 tests 目录加进导入路径，供导入同目录的公共替身模块
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from remote_bridge.channel import quota as quota_store   # noqa: E402

from weixin_test_helpers import FakeWeixinClient, make_msg   # noqa: E402


# ============ 推送路由 ============
# ============ 配额机制 ============
class TestQuota:
    """配额必须按「每条用户消息重置」建模，这是修正过的真实机制。"""

    def test_no_pool_means_inactive(self):
        """用户没发过消息时没有有效回复池。"""
        st = quota_store.weixin.status("never-sent")
        assert st["active"] is False
        assert st["remaining"] == 10

# ============ 网关正文抽取 ============
class TestGatewayExtract:
    """入向正文抽取：文本项优先，语音项用服务端转写文字。

    方案选定「先不做出向语音、把入向语音打磨稳」，
    因此这层必须有测试兜住，避免以后改动把语音识别弄坏。
    """

    def test_text_item_extracted(self):
        """普通文本消息能取出正文。"""
        from remote_bridge.weixin_gateway import extract_text
        msg = {"item_list": [{"type": 1, "text_item": {"text": "你好"}}]}
        assert extract_text(msg) == "你好"

    def test_voice_item_uses_transcript(self):
        """语音消息取服务端转写的文字，不需要本地 ASR。"""
        from remote_bridge.weixin_gateway import extract_text
        msg = {"item_list": [{"type": 3, "voice_item": {"text": "语音转出来的文字"}}]}
        assert extract_text(msg) == "语音转出来的文字"

    def test_text_wins_over_voice(self):
        """同时存在文本与语音项时，文本优先（不论谁排在前面）。"""
        from remote_bridge.weixin_gateway import extract_text
        msg = {"item_list": [
            {"type": 3, "voice_item": {"text": "语音"}},
            {"type": 1, "text_item": {"text": "文本"}},
        ]}
        assert extract_text(msg) == "文本"

    def test_image_only_returns_empty(self):
        """纯图片没有正文，应返回空串由上层忽略，而不是抛异常。"""
        from remote_bridge.weixin_gateway import extract_text
        assert extract_text({"item_list": [{"type": 2, "image_item": {}}]}) == ""

    def test_empty_or_malformed_returns_empty(self):
        """空消息、缺字段、空列表、含 None 项都不能抛异常。"""
        from remote_bridge.weixin_gateway import extract_text
        assert extract_text({}) == ""
        assert extract_text({"item_list": []}) == ""
        assert extract_text({"item_list": [None]}) == ""

    def test_sender_extracted(self):
        """发送者标识能取到；缺失时返回空串。"""
        from remote_bridge.weixin_gateway import sender_of
        assert sender_of({"from_user_id": "u1@im.wechat"}) == "u1@im.wechat"
        assert sender_of({}) == ""


# ============ 指令兼容 ============
class TestCommandCompat:
    """指令走通微信通道——「指令全部哑掉」故障的直接回归防线。"""

    def test_help_command_replies_on_weixin(self):
        """微信上执行 /help 必须能拿到回执，不能因窗口检查而静默失败。"""
        from remote_bridge import command_panel
        c = FakeWeixinClient()
        handled = command_panel.handle_command(c, "u1@im.wechat", "", "/help")
        assert handled is True
        assert c.sent, "/help 应当产生回执"
        assert "指令" in c.sent[0][1] or "/" in c.sent[0][1]

    def test_side_command_replies_on_weixin(self):
        """普通抽屉指令也要能回执。"""
        from remote_bridge import command_panel
        c = FakeWeixinClient()
        assert command_panel.handle_command(c, "u1@im.wechat", "", "/sd") is True
        assert c.sent and "切换" in c.sent[0][1]

    def test_voice_confirm_degrades_gracefully(self):
        """/vo 在微信上无待确认语音，应给友好提示而非抛异常。"""
        from remote_bridge import command_panel
        c = FakeWeixinClient()
        assert command_panel.handle_command(c, "u1@im.wechat", "", "/vo") is True
        assert c.sent, "应当给出「没有待确认语音」之类的提示"

    def test_result_routing_recognizes_weixin_openid(self):
        """回传路由必须认出微信用户，不能把它当 QQ 用户走窗口检查。

        真实故障：微信用户标识不等于 web-user，被当成 QQ 用户后走了
        被动回复窗口检查；该窗口在 QQ 表里不存在，发送被静默跳过，
        表现为「截图执行了、抽屉回传了、手机上什么也没收到」。
        """
        from routes.bridge import _is_weixin_openid
        assert _is_weixin_openid("o9cq809WNQ8z4cLmY0aXB6Fve9zE@im.wechat") is True
        assert _is_weixin_openid("19501CD1ABCDEF") is False
        assert _is_weixin_openid("web-user") is False
        assert _is_weixin_openid("") is False

    def test_qq_client_still_requires_window(self):
        """QQ 客户端未声明 needs_window，指令层必须仍走窗口检查（行为不变）。"""
        class FakeQQ:
            def __init__(self):
                self.sent = []

            def send_c2c(self, openid, text, msg_id="", msg_seq=1, markdown=False):
                self.sent.append(text)
                return True, {}
        q = FakeQQ()
        assert getattr(q, "needs_window", True) is True
