"""公共层 —— 卡片投递的契约测试

测的是 channel/delivery.py，不针对任何具体通道。

为什么这样组织：投递逻辑收归公共层之后，三条通道共用同一份实现。
若测试仍按通道写，每个通道的用例只覆盖自己的调用点，公共层的行为契约
反而无人守护——改坏公共层，各通道测试可能照样全绿。

本文件守住四条契约：
  1. 多图必须合并成**一张**卡片（data_urls 数组），不能逐张投；
  2. 文字随图入同一张卡；无文字时补「用户截图」；
  3. 本地路径与 dataURL 两种来源都能识别，可混用；
  4. 图片全部不可用时返回空串，不抛异常。

运行：python -m pytest tests/test_channel_delivery.py -q
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

import pytest  # noqa: E402
import paths  # noqa: E402,F401  触发路径引导
import channel_binding  # noqa: E402

from remote_bridge.channel import delivery  # noqa: E402


class _FakeBus:
    """记录 create 调用的假投递队列。"""

    def __init__(self):
        """初始化调用记录。"""
        self.calls = []

    def create(self, **kwargs):
        """记录一次建卡并返回带 id 的简单对象。"""
        self.calls.append(kwargs)

        class _Card:
            id = "card-fake-0001"

        return _Card()


@pytest.fixture
def _patch_bus(monkeypatch):
    """把投递队列替换成假实现，返回它以便断言。"""
    fake = _FakeBus()
    monkeypatch.setattr(delivery.delivery_queue, "bus", fake)
    return fake


def test_multi_images_merged_into_one_card(_patch_bus, tmp_path):
    """多张图必须合成一张卡片，且 data_urls 含全部图片。"""
    # 造两张真实的本地图片文件
    paths = []
    for name in ("a.png", "b.png"):
        p = tmp_path / name
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 32)
        paths.append(str(p))

    cid = delivery.deliver_images("wecom", "chat-1", sources=paths)

    assert cid  # 投递成功
    # 关键断言：只建了一张卡片，而不是两张
    assert len(_patch_bus.calls) == 1
    payload = _patch_bus.calls[0]["payload"]
    assert len(payload["data_urls"]) == 2
    assert payload["data_url"] == payload["data_urls"][0]


def test_text_travels_with_images(_patch_bus, tmp_path):
    """同消息文字应随图进入同一张卡片。"""
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 32)

    delivery.deliver_images("wecom", "chat-1", sources=[str(p)], text="这是说明文字")

    payload = _patch_bus.calls[0]["payload"]
    assert payload["text"] == "这是说明文字"


def test_empty_text_falls_back_to_default(_patch_bus, tmp_path):
    """没有文字时补默认说明，给模型上下文。"""
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 32)

    delivery.deliver_images("qq", "openid-1", sources=[str(p)])

    assert _patch_bus.calls[0]["payload"]["text"] == "用户截图"


def test_data_url_and_path_can_mix(_patch_bus, tmp_path):
    """已转好的 dataURL 与本地路径可以混传，两种都要收下。"""
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 32)
    url = "data:image/png;base64,QUJD"

    delivery.deliver_images("web", "web-user", sources=[url, str(p)])

    assert len(_patch_bus.calls[0]["payload"]["data_urls"]) == 2


def test_all_unusable_returns_empty(_patch_bus):
    """图片全部不可用时返回空串，不建卡、不抛异常。"""
    cid = delivery.deliver_images("wecom", "chat-1", sources=["/no/such/file.png"])

    assert cid == ""
    assert _patch_bus.calls == []


def test_extra_fields_passed_through(_patch_bus, tmp_path):
    """extra 字段应透传到 payload（网页版靠它带 image_names）。"""
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 32)

    delivery.deliver_images("web", "web-user", sources=[str(p)],
                            extra={"image_names": ["a.png"]})

    assert _patch_bus.calls[0]["payload"]["image_names"] == ["a.png"]


def test_source_labeled_on_card(_patch_bus, tmp_path):
    """卡片的 source 应等于传入的通道标识，便于前端区分来源。"""
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 32)

    delivery.deliver_images("wecom", "chat-1", sources=[str(p)])

    assert _patch_bus.calls[0]["source"] == "wecom"


def test_bound_image_card_targets_bound_page(_patch_bus, tmp_path):
    """通道绑定页面后，图片卡片的 target_page 等于该页面。"""
    p = tmp_path / "a.png"
    p.write_bytes(b"image-bytes")
    page = "https://chat.deepseek.com/chat/abc"
    channel_binding.reset()
    try:
        channel_binding.bind("qq", page)
        cid = delivery.deliver_images("qq", "openid-1", sources=[str(p)])
        assert cid
        assert _patch_bus.calls[0]["target_page"] == page
    finally:
        channel_binding.reset()
