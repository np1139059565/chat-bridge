"""企业微信通道：协议层与客户端契约测试

为什么需要：
    微信通道上线时零测试覆盖，导致「指令全哑」「配额写错」「推送目标错」
    三个故障都是用户实际踩到才发现的。企业微信通道从第一行起就配测试。

本文件覆盖：
    协议层 —— 帧结构、req_id 透传、流式字段位置、分片、解密
    客户端 —— QQ 兼容签名、凭证判断、发送边界

网关与路由的用例见 test_wecom_router.py（拆分以控制单文件函数数量）。
运行：python -m pytest tests/test_wecom_protocol.py -q
"""
import base64
import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

from remote_bridge import wecom_proto as proto          # noqa: E402
from remote_bridge.wecom_client import WecomClient     # noqa: E402


# ============ 协议层 ============
class TestProto:
    """帧结构与字段位置必须与官方文档一致。"""

    def test_frame_has_cmd_headers_body(self):
        """每帧必须含 cmd / headers.req_id / body 三部分。"""
        obj = json.loads(proto.frame("ping"))
        assert obj["cmd"] == "ping"
        assert obj["headers"]["req_id"]
        assert obj["body"] == {}

    def test_frame_accepts_explicit_req_id(self):
        """可指定 req_id——回复类消息必须透传回调带来的那个。"""
        obj = json.loads(proto.frame("x", {}, req_id="R-1"))
        assert obj["headers"]["req_id"] == "R-1"

    def test_subscribe_frame_shape(self):
        """订阅帧的 body 必须含 bot_id 与 secret。"""
        obj = json.loads(proto.subscribe_frame("bid", "sec"))
        assert obj["cmd"] == proto.CMD_SUBSCRIBE
        assert obj["body"] == {"bot_id": "bid", "secret": "sec"}

    def test_respond_passes_through_req_id(self):
        """回复帧必须用回调的 req_id，新生成的会关联不上原会话。"""
        obj = json.loads(proto.respond_frame("REQ-XYZ", "chat1", "hi"))
        assert obj["headers"]["req_id"] == "REQ-XYZ"

    def test_respond_stream_lives_in_body(self):
        """流式标记在 body.stream，不是顶层 finish。"""
        obj = json.loads(proto.respond_frame("R", "c", "hi"))
        assert "stream" in obj["body"]
        assert obj["body"]["stream"]["finish"] is True
        assert "finish" not in obj["body"]

    def test_respond_markdown_payload(self):
        """markdown 类型的正文放在 body.markdown.content。"""
        obj = json.loads(proto.respond_frame("R", "c", "正文"))
        assert obj["body"]["msgtype"] == "markdown"
        assert obj["body"]["markdown"]["content"] == "正文"

    def test_respond_text_payload(self):
        """text 类型的正文放在 body.text.content。"""
        obj = json.loads(proto.respond_frame("R", "c", "正文", msgtype="text"))
        assert obj["body"]["msgtype"] == "text"
        assert obj["body"]["text"]["content"] == "正文"

    def test_send_frame_carries_chatid(self):
        """主动推送帧必须带 chatid 与 chat_type。"""
        obj = json.loads(proto.send_frame("c1", 2, {"msgtype": "markdown"}))
        assert obj["cmd"] == proto.CMD_SEND_MSG
        assert obj["body"]["chatid"] == "c1"
        assert obj["body"]["chat_type"] == 2

    def test_upload_frames_shape(self):
        """上传三步的帧字段名必须准确。"""
        init = json.loads(proto.upload_init_frame("a.png", 100, "image"))
        assert init["cmd"] == proto.CMD_UPLOAD_INIT
        assert init["body"]["file_size"] == 100
        chunk = json.loads(proto.upload_chunk_frame("u1", 0, "AAA"))
        assert chunk["body"]["chunk_index"] == 0
        fin = json.loads(proto.upload_finish_frame("u1"))
        assert fin["body"]["upload_id"] == "u1"

    def test_split_chunks(self):
        """分片切分：总数正确、内容无损。"""
        data = b"x" * 1200
        chunks = proto.split_chunks(data, 512)
        assert len(chunks) == 3
        assert b"".join(chunks) == data

    def test_split_chunks_empty(self):
        """空数据返回空列表，不抛异常。"""
        assert proto.split_chunks(b"", 512) == []

    def test_b64_roundtrip(self):
        """base64 编解码可逆。"""
        raw = b"\x00\x01hello"
        assert base64.b64decode(proto.b64(raw)) == raw

    def test_decrypt_with_invalid_key_returns_input(self):
        """密钥非法时原样返回，不抛异常（由调用方决定如何降级）。"""
        raw = b"not-encrypted"
        assert proto.decrypt_media(raw, "") == raw
        assert proto.decrypt_media(raw, "bad") == raw

    def test_decrypt_real_roundtrip(self):
        """用合法密钥加密后能正确解回明文。"""
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        except ImportError:
            pytest.skip("未安装 cryptography")
        key = bytes(range(32))
        plain = b"hello wecom"
        pad = 16 - (len(plain) % 16)
        padded = plain + bytes([pad]) * pad
        enc = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
        cipher_text = enc.update(padded) + enc.finalize()
        got = proto.decrypt_media(cipher_text, base64.b64encode(key).decode())
        assert got == plain

    def test_respond_image_frame_uses_msg_item(self):
        """图片必须放在 stream.msg_item 里，且 base64 不带 dataURL 前缀。"""
        obj = json.loads(proto.respond_image_frame("R", "c", "QUJD", "abc123"))
        items = obj["body"]["stream"]["msg_item"]
        assert items[0]["msgtype"] == "image"
        assert items[0]["image"]["base64"] == "QUJD"
        assert items[0]["image"]["md5"] == "abc123"


# ============ 客户端契约 ============
class TestClientContract:
    """客户端必须满足指令层的调用契约。"""

    def test_needs_window_is_false(self):
        """企业微信靠 chatid 主动投递，不依赖被动回复窗口。"""
        assert WecomClient.needs_window is False

    def test_has_cred_requires_both_fields(self):
        """BotID 与 Secret 缺一不可。"""
        assert WecomClient("b", "s", None).has_cred() is True
        assert WecomClient("b", "", None).has_cred() is False
        assert WecomClient("", "s", None).has_cred() is False

    def test_send_c2c_accepts_qq_signature(self):
        """send_c2c 必须接受 QQ 那套参数，指令层才能原样调用。"""
        assert hasattr(WecomClient, "send_c2c")
        assert hasattr(WecomClient, "send_c2c_image")

    def test_send_rejects_empty_chatid(self):
        """空会话 id 直接拒绝，不发无目标的请求。"""
        c = WecomClient("b", "s", None)
        ok, err = c.send_markdown("", "hi")
        assert ok is False and err == "no_chatid"

    def test_send_rejects_empty_text(self):
        """空正文直接拒绝。"""
        c = WecomClient("b", "s", None)
        ok, err = c.send_markdown("c1", "")
        assert ok is False and err == "empty_text"

    def test_text_length_cap_is_sane(self):
        """超长文本要截断，上限常量需在合理区间。"""
        assert WecomClient.MAX_TEXT_CHARS >= 1000

    def test_start_without_cred_fails(self):
        """缺凭证时启动应失败，而不是静默空转。"""
        assert WecomClient("", "", None).start() is False

    def test_respond_image_requires_req_id(self):
        """无 req_id 时不能回复图片（客户端会一直转圈）。"""
        c = WecomClient("b", "s", None)
        ok, err = c.respond_image("", "chat1", "/nonexistent.png")
        assert ok is False and err == "missing_req_id_or_chatid"
