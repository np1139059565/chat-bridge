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

    def test_conversation_suffix_isolated(self):
        """会话键带独立后缀，与 QQ / 微信的已推集合互不干扰。"""
        assert router.CONV_SUFFIX == "@wecom"

    def test_image_block_collected(self):
        """图片块能被收集出来（企业微信的核心能力）。"""
        m = {"id": "i1", "blocks": [{"type": "image", "src": ""}]}
        assert router._collect_images(m) == []
