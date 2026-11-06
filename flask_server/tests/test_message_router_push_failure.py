"""消息路由推送失败与重试测试（message_router 失败路径）

背景：
  message_router 已有窗口与并发锁的测试，但推送失败这条链路一直是盲区。
  失败处理写错的后果不是报错，而是静默丢消息：
  窗口关闭时若误记账，消息永久不再重试；重放时异常若穿透，
  会把 WebSocket 回调线程带崩、连心跳一起断掉。

覆盖点：
  1. push_text：窗口关闭不发送、发送成功与失败都如实返回
  2. push_image：参数缺失、窗口关闭、发送失败
  3. _push_voice_after：正文成功才推语音、推送异常吞掉、临时文件无论如何都删
  4. _prepare_batch：无消息返回 None、无目标转积压、条数上限截断、上限配置异常回退
  5. _replay_last_report：无客户端不启动、重放异常不穿透
  6. get_last_openid / get_window / next_seq 的兜底与过期判断

写法说明：
  断言雷同的用例合并到同一方法内，分段注释说明各自验证什么。

运行：python -m pytest tests/test_message_router_push_failure.py -q
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import message_router as mr
from remote_bridge import window_store


class _FakeClient:
    """模拟 QQClient：记录发送调用，可配置为失败。"""

    def __init__(self, ok=True):
        """
        @param ok 发送结果
        """
        self.ok = ok
        self.texts = []
        self.images = []

    def send_c2c(self, openid, text, msg_id="", msg_seq=1, markdown=False):
        """记录文本推送。"""
        self.texts.append({"text": text, "msg_id": msg_id, "seq": msg_seq, "md": markdown})
        return self.ok, ({} if self.ok else "失败")

    def send_c2c_image(self, openid, path, msg_id="", msg_seq=1):
        """记录图片推送。"""
        self.images.append(path)
        return self.ok, ({} if self.ok else "失败")


class _StateGuard(unittest.TestCase):
    """统一清理 message_router 的模块级状态，避免用例互相污染。"""

    def setUp(self):
        """保存并清空窗口、最近上报、最近客户端与 openid。"""
        self._saved = {
            "windows": dict(mr._windows),
            "report": dict(mr._last_report),
            "client": mr._last_client,
            "openid": mr._last_openid,
        }
        mr._windows.clear()
        mr._last_report.clear()
        mr._last_client = None
        mr._last_openid = ""
        # 落盘也替换成空操作，避免测试把窗口写进真实文件
        self._saved_save = window_store.save_windows
        window_store.save_windows = lambda *a, **k: None

    def tearDown(self):
        """还原全部模块级状态与落盘函数。"""
        mr._windows.clear()
        mr._windows.update(self._saved["windows"])
        mr._last_report.clear()
        mr._last_report.update(self._saved["report"])
        mr._last_client = self._saved["client"]
        mr._last_openid = self._saved["openid"]
        window_store.save_windows = self._saved_save

    @staticmethod
    def _open_window(openid="u1", msg_id="m1", seq=0, seconds=3600):
        """直接写入一个有效窗口。

        @param openid 用户
        @param msg_id 消息 id
        @param seq    起始序号
        @param seconds 有效期秒数
        """
        mr._windows[openid] = {
            "msg_id": msg_id,
            "seq": seq,
            "expire": time.time() + seconds,
        }


class PushTextTest(_StateGuard):
    """文本推送：窗口关闭与成功失败两种结果。"""

    def test_text_push_paths(self):
        """窗口关闭不发请求；成功带 msg_id 与递增序号、markdown 透传；失败如实返回。"""
        closed = _FakeClient()
        self.assertFalse(mr.push_text(closed, "u1", "hi"))
        self.assertEqual(closed.texts, [])
        self._open_window(seq=5)
        client = _FakeClient()
        self.assertTrue(mr.push_text(client, "u1", "hi", markdown=True))
        sent = client.texts[0]
        self.assertEqual((sent["msg_id"], sent["seq"], sent["md"]), ("m1", 6, True))
        self.assertFalse(mr.push_text(_FakeClient(ok=False), "u1", "hi"))


class PushImageTest(_StateGuard):
    """图片推送：参数缺失、窗口关闭、成功与失败。"""

    def test_missing_args_and_closed_window(self):
        """客户端、用户、路径任一为空都返回 False；窗口关闭时不发请求。"""
        self.assertFalse(mr.push_image(None, "u1", "a.png"))
        self.assertFalse(mr.push_image(_FakeClient(), "", "a.png"))
        self.assertFalse(mr.push_image(_FakeClient(), "u1", ""))
        client = _FakeClient()
        self.assertFalse(mr.push_image(client, "u1", "a.png"))
        self.assertEqual(client.images, [])

    def test_success_and_failure(self):
        """成功返回 True；发送失败返回 False，两条路径都真正调用了发送。"""
        self._open_window()
        client = _FakeClient()
        self.assertTrue(mr.push_image(client, "u1", "a.png"))
        self.assertEqual(client.images, ["a.png"])
        self.assertFalse(mr.push_image(_FakeClient(ok=False), "u1", "a.png"))


class PushVoiceAfterTest(_StateGuard):
    """语音补推：正文成功才推、异常吞掉、临时文件必删。"""

    def setUp(self):
        """在父类清理之外，准备一个真实临时文件与推送桩。"""
        super().setUp()
        import tempfile
        self._dir = tempfile.mkdtemp()
        self._file = os.path.join(self._dir, "v.mp3")
        with open(self._file, "wb") as f:
            f.write(b"audio")
        self._saved_push = mr.push_voice

    def tearDown(self):
        """还原桩并清理临时目录。"""
        mr.push_voice = self._saved_push
        import shutil
        shutil.rmtree(self._dir, ignore_errors=True)
        super().tearDown()

    def test_no_path_does_nothing(self):
        """没有预合成路径时直接返回，不碰文件。"""
        removed = []
        saved = mr._remove_voice_file
        mr._remove_voice_file = lambda p: removed.append(p)
        try:
            mr._push_voice_after(_FakeClient(), "u1", {"id": "x"}, {}, True)
        finally:
            mr._remove_voice_file = saved
        self.assertEqual(removed, [])

    def test_text_failed_skips_push_but_removes_file(self):
        """正文推送失败时不推语音，但临时文件仍要删——下轮会重新合成。"""
        pushed = []
        mr.push_voice = lambda *a, **k: pushed.append(a)
        mr._push_voice_after(_FakeClient(), "u1", {"id": "x"}, {"x": self._file}, False)
        self.assertEqual(pushed, [])
        self.assertFalse(os.path.exists(self._file))

    def test_text_ok_pushes_and_cleans(self):
        """正文成功时推送语音并删掉临时文件。"""
        pushed = []
        mr.push_voice = lambda c, o, p: pushed.append(p)
        mr._push_voice_after(_FakeClient(), "u1", {"id": "x"}, {"x": self._file}, True)
        self.assertEqual(pushed, [self._file])
        self.assertFalse(os.path.exists(self._file))

    def test_voice_exception_swallowed(self):
        """语音推送抛异常必须吞掉：语音只是补充，不能影响主流程。"""
        def _boom(*a, **k):
            """模拟语音推送失败。"""
            raise RuntimeError("推不动")
        mr.push_voice = _boom
        mr._push_voice_after(_FakeClient(), "u1", {"id": "x"}, {"x": self._file}, True)
        self.assertFalse(os.path.exists(self._file))


class PrepareBatchTest(_StateGuard):
    """上报预处理：空消息、无目标积压、条数上限、配置异常回退。"""

    def setUp(self):
        """在父类清理之外，记录并替换配置读取。"""
        super().setUp()
        import tool_config
        self._saved_cfg = tool_config.get_value
        self._saved_merge = mr.bridge_store.merge_pending
        self._saved_pending = mr.bridge_store.set_pending
        # 合并积压默认直通，避免依赖真实存储
        mr.bridge_store.merge_pending = lambda c, m: m

    def tearDown(self):
        """还原配置读取与存储桩。"""
        import tool_config
        tool_config.get_value = self._saved_cfg
        mr.bridge_store.merge_pending = self._saved_merge
        mr.bridge_store.set_pending = self._saved_pending
        super().tearDown()

    def _patch_limit(self, value=None, raise_on_get=False):
        """替换配置读取返回值或让其抛异常。

        @param value 返回的配置值
        @param raise_on_get 是否抛异常
        """
        import tool_config

        def _get(*a, **k):
            """模拟配置读取。"""
            if raise_on_get:
                raise RuntimeError("配置坏了")
            return value
        tool_config.get_value = _get

    def test_empty_messages_returns_none(self):
        """没有消息时返回 None，不进入推送。"""
        self.assertIsNone(mr._prepare_batch(_FakeClient(), "c1", {"messages": [], "openid": "u1"}))

    def test_no_openid_goes_pending(self):
        """无推送目标时消息转入积压，返回 None。"""
        got = {}
        mr.bridge_store.set_pending = lambda c, m: got.update({"conv": c, "n": len(m)})
        out = mr._prepare_batch(_FakeClient(), "c1", {"messages": [{"id": "a"}]})
        self.assertIsNone(out)
        self.assertEqual(got["n"], 1)

    def test_limit_from_config(self):
        """条数上限取自配置：超出时只保留最新的一批。"""
        self._patch_limit(2)
        msgs = [{"id": str(i)} for i in range(5)]
        out = mr._prepare_batch(_FakeClient(), "c1", {"messages": msgs, "openid": "u1"})
        self.assertEqual([m["id"] for m in out[1]], ["3", "4"])

    def test_config_exception_falls_back(self):
        """配置读取抛异常时回退默认上限，不影响推送。"""
        self._patch_limit(raise_on_get=True)
        msgs = [{"id": str(i)} for i in range(3)]
        out = mr._prepare_batch(_FakeClient(), "c1", {"messages": msgs, "openid": "u1"})
        self.assertIsNotNone(out)
        self.assertEqual(len(out[1]), 3)


class ReplayTest(_StateGuard):
    """续期重放：无客户端不启动、异常不穿透。"""

    def setUp(self):
        """在父类清理之外，保存线程与重放函数引用。"""
        super().setUp()
        import threading
        self._saved_thread = threading.Thread
        self._saved_handle = mr.handle_report

    def tearDown(self):
        """还原线程与重放函数。"""
        import threading
        threading.Thread = self._saved_thread
        mr.handle_report = self._saved_handle
        super().tearDown()

    def test_no_client_does_nothing(self):
        """没有客户端引用时不启动重放线程。"""
        started = []

        class _Spy:
            def __init__(self, *a, **k):
                """记录被创建。"""
                started.append(1)

            def start(self):
                """记录被启动。"""
                started.append(2)
        import threading
        threading.Thread = _Spy
        mr._replay_last_report()
        self.assertEqual(started, [])

    def test_exception_swallowed(self):
        """单会话重放失败不影响其它会话，也不向外抛。"""
        import threading

        class _Sync:
            def __init__(self, target=None, daemon=None):
                """保存目标函数。"""
                self._target = target

            def start(self):
                """直接在当前线程执行。"""
                if self._target:
                    self._target()
        threading.Thread = _Sync
        mr._last_client = _FakeClient()
        mr._last_report["c1"] = {"messages": [{"id": "a"}]}
        calls = []

        def _boom(client, payload):
            """模拟重放失败。"""
            calls.append(1)
            raise RuntimeError("重放炸了")
        mr.handle_report = _boom
        mr._replay_last_report()
        self.assertEqual(calls, [1])


class WindowHelpersTest(_StateGuard):
    """窗口辅助函数：兜底、过期、序号。"""

    def test_get_last_openid_fallback(self):
        """内存为空时回退到公共层落盘记录；内存有值优先。"""
        from remote_bridge.channel import target
        saved = target.qq.get
        target.qq.get = lambda: "qq-user"
        try:
            self.assertEqual(mr.get_last_openid(), "qq-user")
            mr._last_openid = "mem-user"
            self.assertEqual(mr.get_last_openid(), "mem-user")
        finally:
            target.qq.get = saved

    def test_window_and_seq(self):
        """过期窗口取不到、未过期返回副本；无窗口或过期时序号为 (None, 0)。"""
        self.assertIsNone(mr.get_window("u1"))
        self.assertEqual(mr.next_seq("nobody"), (None, 0))
        self._open_window(seconds=-1)
        self.assertIsNone(mr.get_window("u1"))
        self.assertEqual(mr.next_seq("u1"), (None, 0))
        self._open_window(seconds=3600)
        got = mr.get_window("u1")
        self.assertEqual(got["msg_id"], "m1")
        # 返回的是副本，改动它不能影响内部状态
        got["msg_id"] = "changed"
        self.assertEqual(mr._windows["u1"]["msg_id"], "m1")


if __name__ == "__main__":
    unittest.main()
