"""企业微信媒体收发：帧构造与发送分支的测试。

覆盖三件事：
  1) 图片 / 语音 / 文件三种消息帧的结构正确；
  2) 文件三步上传（init → chunk → finish）能拿到 media_id；
  3) 无 req_id 时主动推送发不了媒体，必须如实返回失败而非假装成功。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_wecom_media -v
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发 core/ 与 tools/ 的路径引导
from remote_bridge import wecom_proto as proto
from remote_bridge.wecom_media import WecomMediaMixin


class _FakeClient(WecomMediaMixin):
    """最小可用的假客户端：记录发出去的帧，并按需伪造应答。"""

    def __init__(self, acks=None):
        """@param acks 按顺序返回的应答列表（每次 _send_wait 取一个）"""
        self.sent = []
        self._acks = list(acks or [])

    def _send_nowait(self, frame_text):
        """记录发出的帧并报成功。"""
        self.sent.append(frame_text)
        return True

    def _send_wait(self, frame_text, req_id, timeout=30):
        """记录发出的帧并返回下一个预置应答。"""
        self.sent.append(frame_text)
        return self._acks.pop(0) if self._acks else {}


class TestMediaFrames(unittest.TestCase):
    """三种媒体帧的结构。"""

    def _stream_of(self, frame_text):
        """取出帧里的 stream 字典。"""
        return json.loads(frame_text)["body"]["stream"]

    def test_image_frame(self):
        """图片帧：msgtype=image，带 base64 与 md5。"""
        f = proto.respond_media_frame("rid", "chat1", proto.image_item("AAA", "BBB"))
        item = self._stream_of(f)["msg_item"][0]
        self.assertEqual(item["msgtype"], "image")
        self.assertEqual(item["image"]["base64"], "AAA")
        self.assertEqual(item["image"]["md5"], "BBB")

    def test_voice_frame(self):
        """语音帧：msgtype=voice，结构与图片同构。"""
        f = proto.respond_media_frame("rid", "chat1", proto.voice_item("AAA", "BBB"))
        item = self._stream_of(f)["msg_item"][0]
        self.assertEqual(item["msgtype"], "voice")
        self.assertEqual(item["voice"]["base64"], "AAA")

    def test_file_frame(self):
        """文件帧：msgtype=file，带 media_id 与文件名。"""
        f = proto.respond_media_frame("rid", "chat1", proto.file_item("mid-1", "a.zip"))
        item = self._stream_of(f)["msg_item"][0]
        self.assertEqual(item["msgtype"], "file")
        self.assertEqual(item["file"]["media_id"], "mid-1")
        self.assertEqual(item["file"]["file_name"], "a.zip")

    def test_caption_goes_to_content(self):
        """说明文字应落在 stream.content，实现图文合一。"""
        f = proto.respond_media_frame("rid", "chat1", proto.image_item("A", "B"),
                                      caption="这是说明")
        self.assertEqual(self._stream_of(f)["content"], "这是说明")

    def test_finish_true_single_frame(self):
        """本工程所有回复都是一次性发完，finish 必须为 True。"""
        f = proto.respond_media_frame("rid", "chat1", proto.image_item("A", "B"))
        self.assertTrue(self._stream_of(f)["finish"])

    def test_req_id_passthrough(self):
        """req_id 必须原样透传，否则回复关联不上原会话。"""
        f = proto.respond_media_frame("my-req", "chat1", proto.image_item("A", "B"))
        self.assertEqual(json.loads(f)["headers"]["req_id"], "my-req")


class TestUploadMedia(unittest.TestCase):
    """文件三步上传。"""

    def setUp(self):
        """准备一个临时文件用于上传。"""
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "a.zip")
        with open(self.path, "wb") as f:
            f.write(b"x" * 1000)

    def tearDown(self):
        """清理临时目录。"""
        self._tmp.cleanup()

    def test_upload_returns_media_id(self):
        """init → chunk → finish 全成功后应拿到 media_id。"""
        acks = [
            {"errcode": 0, "body": {"upload_id": "up-1"}},   # init
            {"errcode": 0},                                     # chunk
            {"errcode": 0, "body": {"media_id": "mid-9"}},    # finish
        ]
        c = _FakeClient(acks)
        media_id, err = c._upload_media(self.path, "file")
        self.assertEqual(err, "")
        self.assertEqual(media_id, "mid-9")
        # 三次请求：init + 1 个分片 + finish
        self.assertEqual(len(c.sent), 3)

    def test_init_timeout_returns_error(self):
        """初始化无应答时应返回明确错误，不能继续往下走。"""
        c = _FakeClient([])
        media_id, err = c._upload_media(self.path, "file")
        self.assertEqual(media_id, "")
        self.assertIn("init_timeout", err)

    def test_missing_upload_id(self):
        """init 应答里没有 upload_id 时应中止。"""
        c = _FakeClient([{"errcode": 0, "body": {}}])
        media_id, err = c._upload_media(self.path, "file")
        self.assertEqual(media_id, "")
        self.assertIn("no_upload_id", err)

    def test_chunk_failure_aborts(self):
        """分片上传失败应立即中止并带上片序号。"""
        acks = [
            {"errcode": 0, "body": {"upload_id": "up-1"}},
            {"errcode": 500, "errmsg": "chunk rejected"},
        ]
        c = _FakeClient(acks)
        media_id, err = c._upload_media(self.path, "file")
        self.assertEqual(media_id, "")
        self.assertIn("chunk_failed", err)

    def test_missing_media_id(self):
        """finish 应答里没有 media_id 时应返回错误。"""
        acks = [
            {"errcode": 0, "body": {"upload_id": "up-1"}},
            {"errcode": 0},
            {"errcode": 0, "body": {}},
        ]
        c = _FakeClient(acks)
        media_id, err = c._upload_media(self.path, "file")
        self.assertEqual(media_id, "")
        self.assertIn("no_media_id", err)


class TestSendMedia(unittest.TestCase):
    """媒体发送分支。"""

    def setUp(self):
        """准备临时目录与测试文件。"""
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.voice = os.path.join(self._tmp.name, "v.amr")
        self.file = os.path.join(self._tmp.name, "a.zip")
        for p in (self.voice, self.file):
            with open(p, "wb") as f:
                f.write(b"x" * 100)

    def tearDown(self):
        """清理临时目录。"""
        self._tmp.cleanup()

    def test_respond_voice_sends_frame(self):
        """语音回复应发出一帧且 msgtype 为 voice。"""
        c = _FakeClient()
        ok, err = c.respond_voice("rid", "chat1", self.voice)
        self.assertTrue(ok)
        item = json.loads(c.sent[0])["body"]["stream"]["msg_item"][0]
        self.assertEqual(item["msgtype"], "voice")

    def test_respond_voice_missing_req_id(self):
        """缺 req_id 时应直接拒绝，不构造帧。"""
        c = _FakeClient()
        ok, err = c.respond_voice("", "chat1", self.voice)
        self.assertFalse(ok)
        self.assertEqual(err, "missing_req_id_or_chatid")
        self.assertEqual(c.sent, [])

    def test_respond_file_uploads_then_sends(self):
        """文件回复应先走三步上传，再发文件帧。"""
        acks = [
            {"errcode": 0, "body": {"upload_id": "up-1"}},
            {"errcode": 0},
            {"errcode": 0, "body": {"media_id": "mid-9"}},
        ]
        c = _FakeClient(acks)
        ok, err = c.respond_file("rid", "chat1", self.file)
        self.assertTrue(ok)
        self.assertEqual(err, {})
        # 最后一帧是文件消息，带 media_id
        item = json.loads(c.sent[-1])["body"]["stream"]["msg_item"][0]
        self.assertEqual(item["msgtype"], "file")
        self.assertEqual(item["file"]["media_id"], "mid-9")

    def test_active_push_file_unsupported(self):
        """主动推送发文件不受支持，应如实返回失败。"""
        c = _FakeClient()
        ok, err = c.send_c2c_file("chat1", self.file)
        self.assertFalse(ok)
        self.assertIn("no_file_support", err)
