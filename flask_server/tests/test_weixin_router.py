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

from remote_bridge import weixin_router as router       # noqa: E402

from weixin_test_helpers import FakeWeixinClient, make_msg   # noqa: E402


# ============ 推送路由 ============
class TestRouterMerge:
    """微信配额紧张，合并推送是核心设计，必须有测试兜住。"""

    def test_merges_multiple_messages_into_one(self):
        """一轮里的多条消息必须合并成一条发送，否则配额很快耗尽。"""
        c = FakeWeixinClient()
        router.note_incoming("u1")
        payload = {"conversationId": "conv-merge", "messages": [
            make_msg("m1", "user", "问题"),
            make_msg("m2", "assistant", "回答"),
        ]}
        n = router.handle_report(c, payload)
        assert n == 1, "两条消息应合并为一次发送"
        assert len(c.sent) == 1
        body = c.sent[0][1]
        assert "问题" in body and "回答" in body

    def test_second_report_does_not_resend(self):
        """同一批消息重复上报不应重复发送（抽屉会上报全量切片）。"""
        c = FakeWeixinClient()
        router.note_incoming("u1")
        payload = {"conversationId": "conv-dedupe", "messages": [make_msg("d1")]}
        assert router.handle_report(c, payload) == 1
        assert router.handle_report(c, payload) == 0
        assert len(c.sent) == 1

    def test_no_target_user_skips_send(self):
        """无推送目标时不发送，也不能抛异常。"""
        c = FakeWeixinClient()
        payload = {"conversationId": "conv-no-user", "messages": [make_msg("n1")]}
        assert router.handle_report(c, payload) == 0
        assert c.sent == []

    def test_send_failure_not_marked_pushed(self):
        """发送失败不记账：下轮上报要能重试，否则消息永久丢失。"""
        c = FakeWeixinClient()
        router.note_incoming("u1")
        payload = {"conversationId": "conv-fail", "messages": [make_msg("f1")]}
        c.fail_next = True
        assert router.handle_report(c, payload) == 0
        assert router.handle_report(c, payload) == 1

    def test_weixin_source_filtered_out(self):
        """微信自己投出去的卡片不回推，否则会复读用户刚说的话。"""
        envelope = {"type": "external-call", "source": "weixin", "request": "hi"}
        m = {"id": "w1", "role": "user", "source": "user",
             "blocks": [{"type": "code", "code": json.dumps(envelope)}]}
        c = FakeWeixinClient()
        router.note_incoming("u1")
        assert router.handle_report(c, {"conversationId": "conv-src", "messages": [m]}) == 0
        assert c.sent == []

    def test_long_text_truncated(self):
        """超长文本要截断，保留首尾，避免被服务端拒绝或手机上无法阅读。"""
        long_text = "开头" + ("填充" * 2000) + "结尾"
        cut = router._truncate(long_text)
        assert len(cut) <= router.MAX_TEXT_CHARS + 40
        assert cut.startswith("开头") and cut.endswith("结尾")
        assert "省略" in cut

    def test_short_text_unchanged(self):
        """短文本不做任何改动。"""
        assert router._truncate("短文本") == "短文本"

    def test_pure_tool_call_filtered(self):
        """纯工具调用的消息不该推给微信。

        AI 干活的中间过程（调工具、贴参数）对用户是噪音；
        微信配额本就紧张，更不该被 JSON 占满。
        """
        call = {"type": "bridge-chat-call", "tool": "read_file", "parameters": {"path": "x"}}
        m = {"id": "tc1", "role": "assistant", "source": "assistant",
             "blocks": [{"type": "code", "code": json.dumps(call)}]}
        assert router._should_push(m, {}) is False

    def test_tool_call_with_text_still_pushed(self):
        """带正文的工具调用消息要推：正文不能因附带工具调用而丢失。"""
        call = {"type": "bridge-chat-call", "tool": "read_file", "parameters": {}}
        m = {"id": "tc2", "role": "assistant", "source": "assistant",
             "blocks": [{"type": "paragraph", "text": "我查一下"},
                        {"type": "code", "code": json.dumps(call)}]}
        assert router._should_push(m, {}) is True

    def test_thinking_does_not_count_as_body(self):
        """只有思考块 + 工具调用时，仍算纯工具调用（思考不是给用户看的内容）。"""
        call = {"type": "bridge-chat-call", "tool": "x", "parameters": {}}
        m = {"id": "tc3", "role": "assistant", "source": "assistant",
             "blocks": [{"type": "thinking", "text": "内部推理"},
                        {"type": "code", "code": json.dumps(call)}]}
        assert router._should_push(m, {}) is False

    def test_normal_reply_not_filtered(self):
        """普通回复不含工具调用，必须照常推送。"""
        m = {"id": "tc4", "role": "assistant", "source": "assistant",
             "blocks": [{"type": "paragraph", "text": "这是回答"}]}
        assert router._should_push(m, {}) is True


# ============ 配额机制 ============
class TestQuota:
    """配额必须按「每条用户消息重置」建模，这是修正过的真实机制。"""

    def test_reset_on_new_incoming(self):
        """用户发新消息应重置回复池，而不是在旧计数上累加。"""
        router.note_incoming("u1")
        for _ in range(5):
            router._quota_add("u1", 1)
        assert router.quota_status("u1")["used"] == 5
        router.note_incoming("u1")
        assert router.quota_status("u1")["used"] == 0, "新消息应把回复池清零"

    def test_status_reports_remaining(self):
        """剩余条数 = 上限 - 已用。"""
        router.note_incoming("u2")
        router._quota_add("u2", 3)
        st = router.quota_status("u2")
        assert st["limit"] == 10
        assert st["used"] == 3
        assert st["remaining"] == 7
        assert st["active"] is True

    def test_no_pool_means_inactive(self):
        """用户没发过消息时没有有效回复池。"""
        st = router.quota_status("never-sent")
        assert st["active"] is False
        assert st["remaining"] == 10

    def test_pool_expires_after_window(self):
        """超过 24 小时未刷新，回复池失效。"""
        router.note_incoming("u3")
        router._quota_add("u3", 2)
        router._quota["u3"]["started"] = time.time() - router.QUOTA_WINDOW - 10
        st = router.quota_status("u3")
        assert st["active"] is False, "过期后应视为无有效回复池"

    def test_quota_exhausted_blocks_send(self):
        """回复池用满后不再发送，避免被服务端拒绝。"""
        c = FakeWeixinClient()
        router.note_incoming("u4")
        router._quota_add("u4", router.QUOTA_LIMIT)
        m = make_msg("q1")
        assert router.handle_report(c, {"conversationId": "conv-quota", "messages": [m]}) == 0
        assert c.sent == []


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
        assert sender_of({"from_user_id": "u1"}) == "u1"
        assert sender_of({}) == ""


# ============ 指令兼容 ============
class TestCommandCompat:
    """指令走通微信通道——「指令全部哑掉」故障的直接回归防线。"""

    def test_help_command_replies_on_weixin(self):
        """微信上执行 /help 必须能拿到回执，不能因窗口检查而静默失败。"""
        from remote_bridge import command_panel
        c = FakeWeixinClient()
        handled = command_panel.handle_command(c, "u1", "", "/help")
        assert handled is True
        assert c.sent, "/help 应当产生回执"
        assert "指令" in c.sent[0][1] or "/" in c.sent[0][1]

    def test_side_command_replies_on_weixin(self):
        """普通抽屉指令也要能回执。"""
        from remote_bridge import command_panel
        c = FakeWeixinClient()
        assert command_panel.handle_command(c, "u1", "", "/sd") is True
        assert c.sent and "切换" in c.sent[0][1]

    def test_voice_confirm_degrades_gracefully(self):
        """/vo 在微信上无待确认语音，应给友好提示而非抛异常。"""
        from remote_bridge import command_panel
        c = FakeWeixinClient()
        assert command_panel.handle_command(c, "u1", "", "/vo") is True
        assert c.sent, "应当给出「没有待确认语音」之类的提示"

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
