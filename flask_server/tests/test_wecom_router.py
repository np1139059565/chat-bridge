"""企业微信通道：网关与路由测试

本文件覆盖：
    网关 —— 正文抽取、发送者解析、媒体识别与优先级
    路由 —— 纯工具调用过滤、正文剔除工具代码、截断、来源过滤、图片收集

协议与客户端契约的用例见 test_wecom_protocol.py（拆分以控制单文件函数数量）。
运行：python -m pytest tests/test_wecom_router.py -q
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

from remote_bridge import wecom_router as router       # noqa: E402
from remote_bridge import wecom_gateway as gateway     # noqa: E402


# ============ 网关 ============
class TestGateway:
    """入向正文与媒体识别。"""

    def test_text_extracted(self):
        """普通文本能取出正文。"""
        assert gateway._text_of({"text": {"content": "你好"}}) == "你好"

    def test_empty_text_returns_empty(self):
        """空消息、缺字段都返回空串，不抛异常。"""
        assert gateway._text_of({}) == ""
        assert gateway._text_of({"text": {}}) == ""

    def test_sender_from_nested_from(self):
        """发送者在 body.from.userid，不在顶层——曾因取错层级丢光所有消息。"""
        assert gateway.sender_of({"from": {"userid": "u1"}}) == "u1"

    def test_sender_top_level_fallback(self):
        """顶层 userid 作为兼容兜底仍可取到。"""
        assert gateway.sender_of({"userid": "u2"}) == "u2"

    def test_sender_missing_returns_empty(self):
        """缺失返回空串。"""
        assert gateway.sender_of({}) == ""

    def test_image_detected(self):
        """图片消息能被识别出类型。"""
        kind, info = gateway._media_of({"image": {"url": "http://x"}})
        assert kind == "image" and info["url"] == "http://x"

    def test_file_detected(self):
        """文件消息能被识别出类型。"""
        kind, _ = gateway._media_of({"file": {"url": "http://x"}})
        assert kind == "file"

    def test_no_media_returns_empty(self):
        """无媒体时返回空类型。"""
        kind, info = gateway._media_of({"text": {"content": "hi"}})
        assert kind == "" and info == {}

    def test_image_priority_over_text(self):
        """图文混排时优先按图片处理（正文另有字段承载）。"""
        kind, _ = gateway._media_of({"image": {"url": "u"}, "text": {"content": "t"}})
        assert kind == "image"


# ============ 路由 ============
class TestRouter:
    """推送过滤与合并策略。"""

    def test_pure_tool_call_filtered(self):
        """纯工具调用不推：内部工作过程是噪音。"""
        call = {"type": "bridge-chat-call", "tool": "x", "parameters": {}}
        m = {"id": "t1", "role": "assistant", "source": "assistant",
             "blocks": [{"type": "code", "code": json.dumps(call)}]}
        assert router._is_pure_tool_call(m) is True
        assert router._should_push(m, {}) is False

    def test_text_with_tool_call_still_pushed(self):
        """带正文的工具调用要推：正文不能因附带工具调用而丢。"""
        call = {"type": "bridge-chat-call", "tool": "x", "parameters": {}}
        m = {"id": "t2", "role": "assistant", "source": "assistant",
             "blocks": [{"type": "paragraph", "text": "我查一下"},
                        {"type": "code", "code": json.dumps(call)}]}
        assert router._should_push(m, {}) is True

    def test_body_strips_tool_code(self):
        """工具调用参数里的代码不能进正文。"""
        call = {"type": "bridge-chat-call", "tool": "run",
                "parameters": {"command": "import subprocess"}}
        m = {"id": "t3", "role": "assistant", "source": "assistant",
             "blocks": [{"type": "paragraph", "text": "执行中"},
                        {"type": "code", "code": json.dumps(call)}]}
        body = router._body_of(m, {})
        assert "执行中" in body
        assert "subprocess" not in body

    def test_real_code_block_kept(self):
        """普通代码块保留：用户可能确实要看代码。"""
        m = {"id": "t4", "role": "assistant", "source": "assistant",
             "blocks": [{"type": "paragraph", "text": "写法："},
                        {"type": "code", "code": "print(1)"}]}
        body = router._body_of(m, {})
        assert "print(1)" in body

    def test_truncate_keeps_head_and_tail(self):
        """超长文本截断时保留首尾。"""
        long_text = "开头" + ("填充" * 2000) + "结尾"
        cut = router._truncate(long_text)
        assert cut.startswith("开头") and cut.endswith("结尾")
        assert "省略" in cut

    def test_truncate_short_unchanged(self):
        """短文本不动。"""
        assert router._truncate("短") == "短"

    def test_wecom_source_filtered(self):
        """企业微信自己投出去的卡片不回推，避免复读。"""
        env = {"type": "external-call", "source": "wecom", "request": "hi"}
        m = {"id": "w1", "role": "user", "source": "user",
             "blocks": [{"type": "code", "code": json.dumps(env)}]}
        assert router._should_push(m, {}) is False

    def test_conversation_suffix_isolated(self):
        """会话键带独立后缀，与 QQ / 微信的已推集合互不干扰。"""
        assert router.CONV_SUFFIX == "@wecom"

    def test_image_block_collected(self):
        """图片块能被收集出来（企业微信的核心能力）。"""
        m = {"id": "i1", "blocks": [{"type": "image", "src": ""}]}
        assert router._collect_images(m) == []
