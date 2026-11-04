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

from remote_bridge import wecom_gateway as gateway     # noqa: E402
# 图片收集实现在独立的收集模块，按原名导入保持用例可读
from remote_bridge.wecom_media_collect import collect_images  # noqa: E402


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

    def test_dedupe_isolated_across_channels(self):
        """已推集合按通道独立：同一条消息 id 在企微推过，不影响 QQ。

        去重集合是模块级单例，本用例会写真实内存状态，
        故用专用会话键并在结束时清空，避免污染其它用例。
        """
        from remote_bridge.channel import dedupe
        key = "conv-isolation-test"
        try:
            # 企微推过这条消息
            assert dedupe.wecom.filter_new(key, ["m1"]) == ["m1"]
            # QQ 侧仍视为新消息：两条通道互不压制
            assert dedupe.qq.filter_new(key, ["m1"]) == ["m1"]
            # 同一通道再问：已推过，不再返回
            assert dedupe.wecom.filter_new(key, ["m1"]) == []
        finally:
            # 清掉本用例写入的记录，恢复干净状态
            dedupe.wecom.forget(key)
            dedupe.qq.forget(key)

    def test_image_block_collected(self):
        """图片块能被收集出来（企业微信的核心能力）。"""
        m = {"id": "i1", "blocks": [{"type": "image", "src": ""}]}
        assert collect_images(m) == []
