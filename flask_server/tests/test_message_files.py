"""本地文件推送测试（message_files 执行路径）

背景：
  该模块负责把电脑上的本地文件通过 QQ 富媒体链路发到手机，
  调用方是工具层的 push_file。它依赖被动回复窗口——窗口关闭时无法主动推送，
  只能等用户下次说话。这条策略若判错，用户会收到「没反应」且不知道为什么。

覆盖点：
  1. 参数缺失时提前返回，不触碰客户端
  2. 窗口关闭时返回明确原因，不调发送
  3. 窗口有效时用正确的 msg_id 与 seq 调用发送
  4. 发送失败时把平台返回原样透传

运行：python -m pytest tests/test_message_files.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import message_files as mf
from remote_bridge import message_router


class FakeClient:
    """QQ 客户端替身：记录调用参数，按预设返回结果。"""

    def __init__(self, ok=True, data=None):
        """
        @param ok   发送是否成功
        @param data 返回的数据
        """
        self.ok = ok
        self.data = data if data is not None else {"id": "sent"}
        self.calls = []

    def send_c2c_file(self, openid, path, msg_id=None, msg_seq=None):
        """记录一次发送调用。

        @returns (ok, data)
        """
        self.calls.append({"openid": openid, "path": path,
                           "msg_id": msg_id, "msg_seq": msg_seq})
        return self.ok, self.data


class PushFileTest(unittest.TestCase):
    """push_file 的主路径与失败路径。"""

    def setUp(self):
        """保存并替换 next_seq，避免依赖真实窗口状态。"""
        self._orig_seq = message_router.next_seq
        self._seq_value = ("msg-1", 1)
        message_router.next_seq = lambda openid: self._seq_value

    def tearDown(self):
        """还原 next_seq。"""
        message_router.next_seq = self._orig_seq

    def test_missing_args_returns_error(self):
        """缺任一参数时提前返回，不调客户端。"""
        client = FakeClient()
        ok, err = mf.push_file(None, "u", "/a")
        self.assertFalse(ok)
        self.assertIn("缺少", err)
        self.assertEqual(client.calls, [])

    def test_missing_openid_returns_error(self):
        """缺接收方时同样提前返回。"""
        ok, err = mf.push_file(FakeClient(), "", "/a")
        self.assertFalse(ok)
        self.assertIn("缺少", err)

    def test_missing_path_returns_error(self):
        """缺文件路径时提前返回。"""
        ok, err = mf.push_file(FakeClient(), "u", "")
        self.assertFalse(ok)
        self.assertIn("缺少", err)

    def test_window_closed_returns_reason(self):
        """窗口关闭时返回可读原因，且不调发送。"""
        self._seq_value = ("", 0)
        client = FakeClient()
        ok, err = mf.push_file(client, "u", "/a")
        self.assertFalse(ok)
        self.assertIn("窗口", err)
        self.assertEqual(client.calls, [])

    def test_success_passes_seq_and_id(self):
        """成功路径：msg_id 与 seq 正确传给客户端。"""
        self._seq_value = ("msg-9", 7)
        client = FakeClient()
        ok, data = mf.push_file(client, "user-1", "/tmp/a.txt")
        self.assertTrue(ok)
        self.assertEqual(len(client.calls), 1)
        call = client.calls[0]
        self.assertEqual(call["openid"], "user-1")
        self.assertEqual(call["path"], "/tmp/a.txt")
        self.assertEqual(call["msg_id"], "msg-9")
        self.assertEqual(call["msg_seq"], 7)
        self.assertEqual(data, {"id": "sent"})

    def test_send_failure_passes_through(self):
        """发送失败时把平台返回原样透传，便于回给用户。"""
        client = FakeClient(ok=False, data={"error": "too large"})
        ok, data = mf.push_file(client, "u", "/a")
        self.assertFalse(ok)
        self.assertEqual(data, {"error": "too large"})


if __name__ == "__main__":
    unittest.main()
