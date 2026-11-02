"""企业微信通道：上报路由层的媒体发送分支测试

本文件覆盖 wecom_router.handle_report 中「媒体怎么发、发不发得出去」：
    1) 有 req_id 时，图片 / 文件 / 语音各发一条；
    2) 无 req_id 时，媒体一律跳过（主动推送不支持媒体）；
    3) 语音受 push["voice"] 开关控制，与 QQ 侧口径一致；
    4) 文本在无 req_id 时走主动推送，仍然发得出去。

为什么要测路由层：test_wecom_send_media.py 只测帧结构与三步上传，
全程用假客户端，路由层的「凭证消费顺序」「开关判定」零覆盖——
而线上「文字能到、媒体全丢」正是这两处出的问题。

运行：python -m pytest tests/test_wecom_media_route.py -q
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

import pytest  # noqa: E402

from remote_bridge import wecom_router as router  # noqa: E402
from remote_bridge import bridge_store          # noqa: E402


class _FakeClient:
    """记录各类媒体发送调用的假客户端。"""

    def __init__(self):
        """初始化调用记录。"""
        self.images = []   # 已发图片路径
        self.files = []    # 已发文件路径
        self.voices = []   # 已发语音路径
        self.texts = []    # 已发文本（主动推送）
        self.replies = []  # 已发回复（带 req_id）

    def respond_image(self, req_id, chatid, path, chat_type=1):
        """记录一次图片回复，报成功。"""
        self.images.append((req_id, path))
        return True, {}

    def respond_file(self, req_id, chatid, path, chat_type=1):
        """记录一次文件回复，报成功。"""
        self.files.append((req_id, path))
        return True, {}

    def respond_voice(self, req_id, chatid, path, chat_type=1):
        """记录一次语音回复，报成功。"""
        self.voices.append((req_id, path))
        return True, {}

    def respond_to(self, req_id, chatid, text, chat_type=1):
        """记录一次带凭证的文本回复，报成功。"""
        self.replies.append((req_id, text))
        return True, {}

    def send_markdown(self, chatid, text, chat_type=1):
        """记录一次主动推送的文本，报成功。"""
        self.texts.append(text)
        return True, {}

    def send_image(self, chatid, path, chat_type=1, caption=""):
        """记录一次主动推送的图片，报成功。"""
        self.images.append(("", path))
        return True, {}

    def send_file(self, chatid, path, chat_type=1, caption=""):
        """记录一次主动推送的文件，报成功。"""
        self.files.append(("", path))
        return True, {}

    def send_voice(self, chatid, path, chat_type=1, caption=""):
        """记录一次主动推送的语音，报成功。"""
        self.voices.append(("", path))
        return True, {}


@pytest.fixture
def _isolate_state(tmp_path, monkeypatch):
    """把去重状态文件与内存缓存都指向临时环境，避免污染生产状态。

    生产状态文件里存着真实会话的已推 id；测试若直接读写它，
    会把假 id 写进去，导致线上拿不存在的用户去发送、每次都被服务端拒绝。
    """
    monkeypatch.setattr(bridge_store, "BRIDGE_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(bridge_store, "_pushed", None)
    monkeypatch.setattr(bridge_store, "_pending_msgs", {})
    # 会话表与待回复凭证都是模块级内存状态，逐用例清空
    monkeypatch.setattr(router, "_chats", {})
    monkeypatch.setattr(router, "_last_req_id", {})
    yield


def _img_msg(mid="m1", path="/tmp/a.png"):
    """构造一条带图片块的消息。"""
    return {"id": mid, "source": "assistant", "role": "assistant",
            "blocks": [{"type": "image", "src": path}]}


def _text_msg(mid="m2"):
    """构造一条纯文本 AI 消息。"""
    return {"id": mid, "source": "assistant", "role": "assistant",
            "blocks": [{"type": "paragraph", "text": "你好"}]}


def _payload(messages, chatid="chat-A"):
    """构造上报体，显式带上企业微信会话，避免依赖「最近活跃会话」。"""
    return {"conversationId": "conv-1", "wecom_chatid": chatid,
            "wecom_chat_type": 1, "messages": messages}


class TestMediaWithoutReqId:
    """无回复凭证时：媒体走主动推送，文本同样走主动推送。"""

    def test_image_active_pushed_without_req_id(self, _isolate_state, monkeypatch):
        """无 req_id 时图片改走主动推送，仍然发出。

        凭证为空串即表示走的是 send_image（主动推送），
        有凭证时该位置会是具体的 rid。
        """
        monkeypatch.setattr(router, "_collect_images", lambda m: ["/tmp/a.png"])
        client = _FakeClient()
        router.handle_report(client, _payload([_img_msg()]))
        assert len(client.images) == 1
        assert client.images[0][0] == ""

    def test_file_and_voice_active_pushed_without_req_id(self, _isolate_state, monkeypatch):
        """无 req_id 时文件与语音同样走主动推送。"""
        monkeypatch.setattr(router, "_collect_images", lambda m: [])
        monkeypatch.setattr(router, "_collect_files", lambda m: ["/tmp/a.zip"])
        monkeypatch.setattr(router, "_collect_voice_files", lambda m: ("/tmp/v.amr", "朗读"))
        monkeypatch.setattr(bridge_store, "get_config", lambda: {"push": {"voice": True}})
        client = _FakeClient()
        router.handle_report(client, _payload([_text_msg()]))
        assert len(client.files) == 1 and client.files[0][0] == ""
        assert len(client.voices) == 1 and client.voices[0][0] == ""

    def test_text_pushed_without_req_id(self, _isolate_state):
        """无 req_id 时文本走主动推送，仍然发得出去。"""
        client = _FakeClient()
        router.handle_report(client, _payload([_text_msg()]))
        assert len(client.texts) == 1
        assert client.replies == []


class TestMediaWithReqId:
    """有回复凭证时：媒体优先发送，凭证被消费。"""

    def test_image_sent_with_req_id(self, _isolate_state, monkeypatch):
        """有 req_id 时图片应发出，并带上该凭证。"""
        monkeypatch.setattr(router, "_collect_images", lambda m: ["/tmp/a.png"])
        router.note_chat("chat-A", 1, "u1", req_id="rid-1")
        client = _FakeClient()
        router.handle_report(client, _payload([_img_msg()]))
        assert [r[0] for r in client.images] == ["rid-1"]

    def test_single_req_id_then_active_push(self, _isolate_state, monkeypatch):
        """只有一个凭证时：第一张走凭证回复，第二张走主动推送。

        凭证不够并不等于发不出去——主动推送不依赖凭证，
        故两张图都应发出，只是路径不同（第一张带 rid，第二张为空）。
        """
        monkeypatch.setattr(router, "_collect_images", lambda m: ["/tmp/a.png", "/tmp/b.png"])
        router.note_chat("chat-A", 1, "u1", req_id="rid-1")
        client = _FakeClient()
        router.handle_report(client, _payload([_img_msg()]))
        assert [r[0] for r in client.images] == ["rid-1", ""]

    def test_queued_req_ids_send_multiple_media(self, _isolate_state, monkeypatch):
        """凭证池化后：两条入向消息带来两个凭证，两张图应各用一张全部发出。

        这正是「一批里有多张图却只收到第一张」的修复目标。
        """
        monkeypatch.setattr(router, "_collect_images", lambda m: ["/tmp/a.png", "/tmp/b.png"])
        # 模拟用户连发两条消息，各带来一个 req_id
        router.note_chat("chat-A", 1, "u1", req_id="rid-1")
        router.note_chat("chat-A", 1, "u1", req_id="rid-2")
        client = _FakeClient()
        router.handle_report(client, _payload([_img_msg()]))
        assert [r[0] for r in client.images] == ["rid-1", "rid-2"]

    def test_req_id_queue_capped(self, _isolate_state):
        """凭证队列有上限，超出的丢最旧的，避免无限堆积。"""
        for i in range(router.MAX_REQ_IDS + 5):
            router.note_chat("chat-A", 1, "u1", req_id="rid-%d" % i)
        q = router._last_req_id.get("chat-A") or []
        assert len(q) == router.MAX_REQ_IDS
        # 最旧的应被丢弃，队头是第 5 个
        assert q[0] == "rid-5"


class TestVoiceSwitch:
    """语音受 push[\"voice\"] 开关控制，与 QQ 侧口径一致。"""

    def test_voice_skipped_when_switch_off(self, _isolate_state, monkeypatch):
        """开关关闭时，即便有语音也不发。"""
        monkeypatch.setattr(router, "_collect_voice_files", lambda m: ("/tmp/v.amr", "朗读"))
        monkeypatch.setattr(bridge_store, "get_config", lambda: {"push": {"voice": False}})
        router.note_chat("chat-A", 1, "u1", req_id="rid-1")
        client = _FakeClient()
        router.handle_report(client, _payload([_text_msg()]))
        assert client.voices == []

    def test_voice_sent_when_switch_on(self, _isolate_state, monkeypatch):
        """开关打开、且有凭证时，语音应发出。"""
        monkeypatch.setattr(router, "_collect_voice_files", lambda m: ("/tmp/v.amr", "朗读"))
        monkeypatch.setattr(bridge_store, "get_config", lambda: {"push": {"voice": True}})
        router.note_chat("chat-A", 1, "u1", req_id="rid-1")
        client = _FakeClient()
        router.handle_report(client, _payload([_text_msg()]))
        assert len(client.voices) == 1
