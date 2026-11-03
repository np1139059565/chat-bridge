"""企业微信通道：上报路由层的媒体发送分支测试

本文件覆盖 wecom_router.handle_report 中「媒体怎么发、发不发得出去」：
    1) 图片 / 文件 / 语音一律走主动推送，不依赖任何回复凭证；
    2) 语音受 push["voice"] 开关控制，与 QQ 侧口径一致；
    3) 文本同样走主动推送，且这批消息处理完后被记为已推。

为什么要测路由层：test_wecom_send_media.py 只测帧结构与三步上传，
全程用假客户端，路由层的「媒体收集」「开关判定」「记账」零覆盖——
而线上「文字能到、媒体全丢」正是这几处出的问题。

运行：python -m pytest tests/test_wecom_media_route.py -q
"""
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
    """记录各类发送调用的假客户端。

    主动推送与凭证回复分别记在不同的列表里：
    前者用于断言「消息确实发出去了」，后者用于断言「压根没走那条路」。
    """

    def __init__(self):
        """初始化各调用记录为空列表。"""
        self.images = []    # 主动推送的图片路径
        self.files = []     # 主动推送的文件路径
        self.voices = []    # 主动推送的语音路径
        self.texts = []     # 主动推送的文本
        self.responds = []  # 凭证回复调用，任何一条都说明凭证逻辑没剔干净

    def send_image(self, chatid, path, chat_type=1, caption=""):
        """记录一次主动推送的图片，报成功。"""
        self.images.append(path)
        return True, {}

    def send_file(self, chatid, path, chat_type=1, caption=""):
        """记录一次主动推送的文件，报成功。"""
        self.files.append(path)
        return True, {}

    def send_voice(self, chatid, path, chat_type=1, caption=""):
        """记录一次主动推送的语音，报成功。"""
        self.voices.append(path)
        return True, {}

    def send_markdown(self, chatid, text, chat_type=1):
        """记录一次主动推送的文本，报成功。"""
        self.texts.append(text)
        return True, {}

    def respond_to(self, req_id, chatid, text, chat_type=1):
        """凭证回复文本：只记账，测试断言此处应为空。"""
        self.responds.append(("text", req_id))
        return True, {}

    def respond_image(self, req_id, chatid, path, chat_type=1):
        """凭证回复图片：只记账，测试断言此处应为空。"""
        self.responds.append(("image", req_id))
        return True, {}

    def respond_file(self, req_id, chatid, path, chat_type=1):
        """凭证回复文件：只记账，测试断言此处应为空。"""
        self.responds.append(("file", req_id))
        return True, {}

    def respond_voice(self, req_id, chatid, path, chat_type=1):
        """凭证回复语音：只记账，测试断言此处应为空。"""
        self.responds.append(("voice", req_id))
        return True, {}


@pytest.fixture
def _isolate_state(tmp_path, monkeypatch):
    """把去重状态文件与内存缓存都指向临时环境，避免污染生产状态。

    生产状态文件里存着真实会话的已推 id；测试若直接读写它，
    会把假 id 写进去，导致线上拿不存在的用户去发送、每次都被服务端拒绝。
    """
    # 状态文件改到临时目录，用完即弃
    monkeypatch.setattr(bridge_store, "BRIDGE_STATE_PATH", tmp_path / "state.json")
    # 已推集合的内存缓存置空，强制从临时文件重新加载
    monkeypatch.setattr(bridge_store, "_pushed", None)
    # 待推缓存同样清空，避免上一用例的失败消息串进本轮
    monkeypatch.setattr(bridge_store, "_pending_msgs", {})
    # 会话表是模块级内存状态，逐用例清空
    monkeypatch.setattr(router, "_chats", {})
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


class TestMediaActivePush:
    """三类媒体一律走主动推送，且不触碰凭证回复接口。"""

    def test_image_active_pushed(self, _isolate_state, monkeypatch):
        """图片应经 send_image 发出，且不调用 respond_image。"""
        # 绕过落盘，直接给出一条图片路径
        monkeypatch.setattr(router, "_collect_images", lambda m: ["/tmp/a.png"])
        client = _FakeClient()
        router.handle_report(client, _payload([_img_msg()]))
        # 图片确实发出去了
        assert client.images == ["/tmp/a.png"]
        # 且没有走任何凭证回复接口
        assert client.responds == []

    def test_file_and_voice_active_pushed(self, _isolate_state, monkeypatch):
        """文件与语音同样经主动推送发出。"""
        # 本用例只关心文件与语音，图片收集置空
        monkeypatch.setattr(router, "_collect_images", lambda m: [])
        # 直接给出一条文件路径
        monkeypatch.setattr(router, "_collect_files", lambda m: ["/tmp/a.zip"])
        # 直接给出一条语音路径与朗读文本
        monkeypatch.setattr(router, "_collect_voice_files",
                            lambda m, vm=None: ("/tmp/v.amr", "朗读"))
        # 语音开关打开
        monkeypatch.setattr(bridge_store, "get_config", lambda: {"push": {"voice": True}})
        client = _FakeClient()
        router.handle_report(client, _payload([_text_msg()]))
        # 文件与语音各自发出一次
        assert client.files == ["/tmp/a.zip"]
        assert client.voices == ["/tmp/v.amr"]
        # 没有任何凭证回复
        assert client.responds == []

    def test_text_pushed_and_marked(self, _isolate_state):
        """文本走主动推送，并在这批处理后记为已推，下轮不再重复。"""
        client = _FakeClient()
        router.handle_report(client, _payload([_text_msg()]))
        # 文本已发出
        assert len(client.texts) == 1
        # 走的是主动推送而非凭证回复
        assert client.responds == []
        # 该消息已记入已推集合（会话键带 @wecom 后缀）
        assert "m2" in bridge_store.get_pushed_set("conv-1@wecom")

    def test_media_batch_fully_sent(self, _isolate_state, monkeypatch):
        """一批里有多张图时全部发出，不再受「一个凭证只回一条」限制。"""
        # 一次给两张图，模拟「多图只收到第一张」的历史故障场景
        monkeypatch.setattr(router, "_collect_images", lambda m: ["/tmp/a.png", "/tmp/b.png"])
        client = _FakeClient()
        router.handle_report(client, _payload([_img_msg()]))
        # 两张都必须发出去
        assert client.images == ["/tmp/a.png", "/tmp/b.png"]


class TestVoiceSwitch:
    """语音受 push["voice"] 开关控制，与 QQ 侧口径一致。"""

    def test_voice_skipped_when_switch_off(self, _isolate_state, monkeypatch):
        """开关关闭时，即便能取到语音也不发。"""
        # 语音路径能取到，但开关是关的
        monkeypatch.setattr(router, "_collect_voice_files", lambda m, vm=None: ("/tmp/v.amr", "朗读"))
        monkeypatch.setattr(bridge_store, "get_config", lambda: {"push": {"voice": False}})
        client = _FakeClient()
        router.handle_report(client, _payload([_text_msg()]))
        # 一条语音都不该发出
        assert client.voices == []

    def test_voice_sent_when_switch_on(self, _isolate_state, monkeypatch):
        """开关打开时，语音正常发出。"""
        # 语音路径与开关都就位
        monkeypatch.setattr(router, "_collect_voice_files",
                            lambda m, vm=None: ("/tmp/v.amr", "朗读"))
        monkeypatch.setattr(bridge_store, "get_config", lambda: {"push": {"voice": True}})
        client = _FakeClient()
        router.handle_report(client, _payload([_text_msg()]))
        # 语音恰好发出一次
        assert client.voices == ["/tmp/v.amr"]
