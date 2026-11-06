"""QQ 富媒体发送测试（qq_media 执行路径）

背景：
  该模块此前零覆盖。图片、语音、文件三种富媒体都走它，
  file_type 用错会让平台把图片当文件、把语音当图片，
  表现为对方收到一条空白消息或直接报错；
  上传成功但漏发消息，则是「上传了却没送达」，最难排查。

覆盖点：
  1. Base64 编码：内容可还原、结果可 JSON 序列化、空文件
  2. 三种上传：file_type 分别是 1 / 3 / 4，文件上传必带 file_name
  3. 上传失败：HTTP 错误带详情、普通异常、响应缺 file_info
  4. 发送富媒体：msg_type=7、media.file_info 正确、成功与两种失败
  5. 三个对外入口：无 token 短路、读文件失败、上传失败不再发送、全链路成功

写法说明：
  同一主题下断言雷同的用例合并为一个方法内的多段断言，含义写在注释里。

运行：python -m pytest tests/test_qq_media.py -q
"""
import base64
import io
import os
import sys
import tempfile
import unittest
import urllib.error
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge.qq_media import QqMediaMixin


def _http_error(code, body=b""):
    """构造带响应体的 HTTPError，模拟平台拒绝。

    @param code HTTP 状态码
    @param body 响应体字节
    """
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(body))


class _Host(QqMediaMixin):
    """模拟宿主：提供 mixin 依赖的四项基础能力。

    用一个独立类而非 QQClient，避免把 WebSocket 那套无关状态带进测试。
    """

    def __init__(self, token="tok", upload=None, send=None):
        """
        @param token  是否视为有可用 token
        @param upload 上传时调用的假实现
        @param send   发送时调用的假实现
        """
        self._has_token = bool(token)
        self._upload = upload
        self._send = send
        self.calls = []

    def _ensure_token(self):
        """返回预设的 token 有效性。"""
        return self._has_token

    def _auth_header(self):
        """固定鉴权头，便于断言请求带上了鉴权。"""
        return {"Authorization": "QQBot tok"}

    def _http_error_detail(self, e):
        """读取错误响应体；读不出来返回空串。"""
        try:
            return e.read().decode("utf-8")
        except Exception:
            return ""

    def _http_post(self, url, body, headers=None):
        """按调用类型分派到假的上传或发送实现。

        以 URL 结尾区分：/files 为上传，/messages 为发送。
        """
        self.calls.append({"url": url, "body": body, "headers": headers})
        if url.endswith("/files"):
            return self._upload(url, body, headers) if self._upload else {}
        return self._send(url, body, headers) if self._send else {}


class B64AndUploadTest(unittest.TestCase):
    """Base64 编码与三种上传的请求体契约。"""

    def setUp(self):
        """独立临时目录。"""
        self._dir = tempfile.mkdtemp()

    def tearDown(self):
        """清理。"""
        shutil.rmtree(self._dir, ignore_errors=True)

    def _write(self, name, data):
        """写入测试文件并返回路径。"""
        p = os.path.join(self._dir, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def test_read_file_b64(self):
        """编码结果可还原、是可放进 JSON 的 ASCII 串；空文件编码为空串。"""
        p = self._write("a.bin", b"\x00\x01hello")
        out = _Host()._read_file_b64(p)
        self.assertEqual(base64.b64decode(out), b"\x00\x01hello")
        self.assertIsInstance(out, str)
        out.encode("ascii")
        self.assertEqual(_Host()._read_file_b64(self._write("c.bin", b"")), "")

    @staticmethod
    def _capture(file_info="fi-x"):
        """构造一个记录请求体并返回 file_info 的假上传。

        @param file_info 上传响应里的 file_info
        @returns (记录字典, 假上传函数)
        """
        seen = {}

        def _up(url, body, headers):
            """记录上传请求体。"""
            seen.update(body)
            seen["_url"] = url
            return {"file_info": file_info}
        return seen, _up

    def test_file_types(self):
        """图片=1、语音=3、文件=4；三者都不让平台代为发送。"""
        for method, want in (("_upload_image", 1), ("_upload_voice", 3)):
            seen, up = self._capture()
            info, err = getattr(_Host(upload=up), method)("u1", "QUJD")
            self.assertEqual((info, err), ("fi-x", ""), "方法=%s" % method)
            self.assertEqual(seen["file_type"], want, "方法=%s" % method)
            self.assertFalse(seen["srv_send_msg"])
            self.assertEqual(seen["file_data"], "QUJD")
        # 文件上传还必须带 file_name，否则对方看不到文件名与扩展名
        seen, up = self._capture("fi-3")
        info, err = _Host(upload=up)._upload_file("u1", "QUJD", "报表.xlsx")
        self.assertEqual((info, err), ("fi-3", ""))
        self.assertEqual((seen["file_type"], seen["file_name"]), (4, "报表.xlsx"))

    def test_upload_url(self):
        """上传地址必须带接收方 openid，并以 /files 结尾。"""
        seen, up = self._capture("fi")
        _Host(upload=up)._upload_image("openid-xyz", "QQ==")
        self.assertIn("openid-xyz", seen["_url"])
        self.assertTrue(seen["_url"].endswith("/files"))

    def test_upload_failures(self):
        """HTTP 错误带状态码与平台说明；普通异常转字符串；缺 file_info 返回空串。"""
        def _413(url, body, headers):
            """模拟 413 内容过大。"""
            raise _http_error(413, "文件过大".encode("utf-8"))
        info, err = _Host(upload=_413)._upload_image("u1", "QQ==")
        self.assertEqual(info, "")
        self.assertIn("413", err)
        self.assertIn("文件过大", err)

        def _conn(url, body, headers):
            """模拟连接失败。"""
            raise ConnectionError("断网")
        info, err = _Host(upload=_conn)._upload_voice("u1", "QQ==")
        self.assertEqual(info, "")
        self.assertIn("断网", err)
        self.assertEqual(_Host(upload=lambda *a: {})._upload_image("u1", "QQ=="), ("", ""))


class SendMediaTest(unittest.TestCase):
    """发送富媒体：msg_type=7 与 media 结构是平台契约。"""

    def test_body_shape(self):
        """正文为空、类型为 7、file_info 放进 media，并带被动回复字段。"""
        seen = {}

        def _send(url, body, headers):
            """记录发送请求体。"""
            seen.update(body)
            return {"id": "m9"}
        ok, data = _Host(send=_send)._send_media("u1", "fi-1", "msg-a", 2)
        self.assertTrue(ok)
        self.assertEqual(data["id"], "m9")
        self.assertEqual(seen["msg_type"], 7)
        self.assertEqual(seen["content"], "")
        self.assertEqual(seen["media"]["file_info"], "fi-1")
        self.assertEqual((seen["msg_id"], seen["msg_seq"]), ("msg-a", 2))

    def test_error_paths(self):
        """发送被拒带状态码；普通异常转字符串。"""
        def _403(url, body, headers):
            """模拟 403。"""
            raise _http_error(403, "无权限".encode("utf-8"))
        ok, err = _Host(send=_403)._send_media("u1", "fi", "m", 1)
        self.assertFalse(ok)
        self.assertIn("403", err)

        def _timeout(url, body, headers):
            """模拟超时。"""
            raise TimeoutError("超时")
        ok, err = _Host(send=_timeout)._send_media("u1", "fi", "m", 1)
        self.assertFalse(ok)
        self.assertIn("超时", err)


class SendEntryTest(unittest.TestCase):
    """三个对外入口：两步流程中任一步失败都不能继续下一步。"""

    def setUp(self):
        """独立临时目录与一个真实文件。"""
        self._dir = tempfile.mkdtemp()
        self._file = os.path.join(self._dir, "x.bin")
        with open(self._file, "wb") as f:
            f.write(b"payload")

    def tearDown(self):
        """清理。"""
        shutil.rmtree(self._dir, ignore_errors=True)

    @staticmethod
    def _spy_send(calls):
        """构造一个记录发送调用的假实现。

        @param calls 记录列表
        @returns 假发送函数
        """
        def _send(url, body, headers):
            """记录并返回成功。"""
            calls.append(body)
            return {"id": "ok"}
        return _send

    def test_no_token_all_entries(self):
        """三个入口在无 token 时都直接返回 no_token。"""
        h = _Host(token="")
        for method in (h.send_c2c_image, h.send_c2c_voice, h.send_c2c_file):
            self.assertEqual(method("u1", self._file), (False, "no_token"),
                             "入口=%s" % method.__name__)

    def test_read_failure_skips_upload(self):
        """文件读不到时返回 read_file_failed，不上传也不发送。"""
        h = _Host()
        ok, err = h.send_c2c_image("u1", os.path.join(self._dir, "nope.png"))
        self.assertFalse(ok)
        self.assertIn("read_file_failed", err)
        self.assertEqual(h.calls, [])
        # 空路径同样在读文件阶段失败
        h = _Host()
        ok, err = h.send_c2c_file("u1", "")
        self.assertFalse(ok)
        self.assertIn("read_file_failed", err)
        self.assertEqual(h.calls, [])

    def test_upload_failure_skips_send(self):
        """上传失败或没拿到 file_info 时都不得再发消息。"""
        calls = []

        def _up(url, body, headers):
            """模拟上传失败。"""
            raise _http_error(500, b"boom")
        h = _Host(upload=_up, send=self._spy_send(calls))
        ok, err = h.send_c2c_image("u1", self._file)
        self.assertFalse(ok)
        self.assertIn("upload", err)
        self.assertEqual(calls, [])
        h = _Host(upload=lambda *a: {}, send=self._spy_send(calls))
        self.assertEqual(h.send_c2c_image("u1", self._file), (False, "no_file_info"))
        self.assertEqual(calls, [])

    def test_image_full_chain(self):
        """全链路成功：先上传后发送，返回服务端响应。"""
        calls = []
        h = _Host(upload=lambda *a: {"file_info": "fi-x"}, send=self._spy_send(calls))
        ok, data = h.send_c2c_image("u1", self._file, msg_id="m1", msg_seq=2)
        self.assertTrue(ok)
        self.assertEqual(data["id"], "ok")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["media"]["file_info"], "fi-x")

    def test_voice_and_file_full_chain(self):
        """语音上传用 file_type=3；文件上传带的是文件名而非整条路径。"""
        types = []

        def _up_voice(url, body, headers):
            """记录 file_type。"""
            types.append(body["file_type"])
            return {"file_info": "fi-v"}
        h = _Host(upload=_up_voice, send=lambda *a: {"id": "ok"})
        ok, _ = h.send_c2c_voice("u1", self._file)
        self.assertTrue(ok)
        self.assertEqual(types, [3])
        seen = {}

        def _up_file(url, body, headers):
            """记录 file_name 与 file_type。"""
            seen.update(body)
            return {"file_info": "fi-f"}
        h = _Host(upload=_up_file, send=lambda *a: {"id": "ok"})
        ok, _ = h.send_c2c_file("u1", self._file)
        self.assertTrue(ok)
        self.assertEqual((seen["file_name"], seen["file_type"]), ("x.bin", 4))


if __name__ == "__main__":
    unittest.main()
