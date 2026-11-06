"""QQ 事件分发测试（qq_gateway 执行路径）

背景：
  该模块此前覆盖率 11%。它是 QQ 通道收消息的入口：
  事件分派错了，用户发什么都石沉大海；指令与聊天通道若串了，
  用户打错的命令会被当成聊天内容转给 AI，控制意图泄漏。

覆盖点：
  1. handle_event：非单聊事件忽略、缺 openid 忽略、空内容且非富媒体忽略
  2. 窗口续期：有 msg_id 时刷新窗口、登记最近用户与活跃渠道；无 msg_id 时跳过
  3. 富媒体优先级：语音 > 图片 > 文件，命中即消费
  4. 文本分派：斜杠被认领走指令、未认领只回提示不投 AI、普通消息投卡片
  5. 语音链路：开关关闭丢弃、开关打开起后台线程、识别成功后先暂存再回发、
     下载失败与识别失败各自的提示分支
  6. 图片链路：下载失败直接返回、成功时投图片卡片、下载与回收的真实路径
  7. 回复辅助：无客户端、窗口关闭、发送失败三条分支
  8. 卡片拼装：语音确认场景在正文前附 voice 提示

写法说明：
  断言雷同的用例合并到同一方法内，分段注释说明各自验证什么。

运行：python -m pytest tests/test_qq_gateway.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import qq_gateway as qg
from remote_bridge.channel import delivery


class _SendingClient:
    """模拟 QQClient：只需能发被动回复，记录发过什么、可配置成败。"""

    def __init__(self, ok=True):
        """
        @param ok 发送结果
        """
        self.ok = ok
        self.sent = []

    def send_c2c(self, openid, text, msg_id="", msg_seq=1, markdown=False):
        """记录一次被动回复，返回成功与否。"""
        self.sent.append({"text": text, "msg_id": msg_id, "seq": msg_seq})
        return self.ok, ({} if self.ok else "失败")


class _Base(unittest.TestCase):
    """公共夹具：替换所有外部依赖并记录调用。"""

    def setUp(self):
        """保存原依赖，替换为可记录的桩。"""
        self.calls = {"note": [], "target": [], "active": [], "cards": [], "images": [], "replies": []}
        self._saved = {
            "dump": qg._dump_raw_event,
            "extract": qg._extract,
            "voice": qg._extract_voice,
            "image": qg._extract_image,
            "file": qg._extract_file,
            "download": qg._download_file,
            "datasrc": qg._to_data_url,
            "note": qg.message_router.note_incoming,
            "seq": qg.message_router.next_seq,
            "deliver_text": delivery.deliver_text,
            "deliver_images": delivery.deliver_images,
        }
        # 默认：无富媒体、无正文、openid 空，各用例按需覆盖
        qg._dump_raw_event = lambda data: None
        qg._extract = lambda data: ("", "", "")
        qg._extract_voice = lambda data: ""
        qg._extract_image = lambda data: ""
        qg._extract_file = lambda data: ("", "")
        qg.message_router.note_incoming = (
            lambda openid, msg_id, client=None: self.calls["note"].append((openid, msg_id)))
        qg.message_router.next_seq = lambda openid: ("m1", 1)
        delivery.deliver_text = self._record("cards")
        delivery.deliver_images = self._record("images")

    def tearDown(self):
        """还原全部被替换的依赖。"""
        qg._dump_raw_event = self._saved["dump"]
        qg._extract = self._saved["extract"]
        qg._extract_voice = self._saved["voice"]
        qg._extract_image = self._saved["image"]
        qg._extract_file = self._saved["file"]
        qg._download_file = self._saved["download"]
        qg._to_data_url = self._saved["datasrc"]
        qg.message_router.note_incoming = self._saved["note"]
        qg.message_router.next_seq = self._saved["seq"]
        delivery.deliver_text = self._saved["deliver_text"]
        delivery.deliver_images = self._saved["deliver_images"]

    def _record(self, key):
        """构造一个把调用记入 self.calls 的投递桩。

        @param key 记录到哪个列表
        @returns 桩函数
        """
        def _stub(channel, openid, *a, **k):
            """记录一次投递。"""
            self.calls[key].append({"channel": channel, "openid": openid, "args": a, "kw": k})
        return _stub

    @staticmethod
    def _gateway(client=None, on_command=None):
        """构造网关实例并注入客户端。

        @param client 假客户端
        @param on_command 指令回调
        @returns QqGateway
        """
        g = qg.QqGateway(on_command=on_command)
        g.qq_client = client
        return g


class HandleEventTest(_Base):
    """事件入口：过滤无关事件与残缺数据。"""

    def test_ignores_invalid_events(self):
        """非单聊事件、缺 openid、空内容且无富媒体，三者都不继续处理。"""
        g = self._gateway()
        g.handle_event("OTHER_EVENT", {})
        g.handle_event(qg.EVENT_C2C_MESSAGE, {})
        self.assertEqual(self.calls["note"], [])
        qg._extract = lambda data: ("u1", "", "m1")
        g.handle_event(qg.EVENT_C2C_MESSAGE, {})
        self.assertEqual(self.calls["cards"], [])

    def test_window_and_channel_notes(self):
        """有 msg_id 时刷新窗口、登记最近用户与活跃渠道。"""
        qg._extract = lambda data: ("u1", "hi", "m1")
        from remote_bridge.channel import target as target_store
        import active_channel
        saved = (target_store.qq.note, active_channel.note)
        target_store.qq.note = lambda o: self.calls["target"].append(o)
        active_channel.note = lambda c: self.calls["active"].append(c)
        try:
            self._gateway().handle_event(qg.EVENT_C2C_MESSAGE, {})
        finally:
            target_store.qq.note, active_channel.note = saved
        self.assertEqual(self.calls["note"], [("u1", "m1")])
        self.assertEqual(self.calls["target"], ["u1"])
        self.assertEqual(self.calls["active"], ["qq"])

    def test_no_msg_id_skips_window(self):
        """没有 msg_id 时不刷新窗口。"""
        qg._extract = lambda data: ("u1", "hi", "")
        import active_channel
        saved = active_channel.note
        active_channel.note = lambda c: None
        try:
            self._gateway().handle_event(qg.EVENT_C2C_MESSAGE, {})
        finally:
            active_channel.note = saved
        self.assertEqual(self.calls["note"], [])


class MediaPriorityTest(_Base):
    """富媒体分派：语音优先于图片，图片优先于文件。"""

    def test_priority_order(self):
        """三者同时存在只处理语音；无语音时处理图片并带上正文。"""
        seen = []
        g = self._gateway()
        g._handle_voice = lambda o, u, m: seen.append("voice")
        g._handle_image = lambda o, u, m, t="": seen.append(("image", t))
        g._handle_file = lambda *a: seen.append("file")
        qg._extract_voice = lambda d: "http://v.silk"
        qg._extract_image = lambda d: "http://i.png"
        self.assertTrue(g._handle_media("u1", {}, "m1", "正文"))
        self.assertEqual(seen, ["voice"])
        # 去掉语音后：图片胜出，且同消息正文被一并传入（图文消息不丢文字）
        qg._extract_voice = lambda d: ""
        self.assertTrue(g._handle_media("u1", {}, "m1", "正文"))
        self.assertEqual(seen[-1], ("image", "正文"))

    def test_file_only_and_none(self):
        """只有文件时处理文件并透传文件名；三者都没有时返回 False。"""
        got = {}
        g = self._gateway()
        g._handle_file = lambda o, u, n, m: got.update({"url": u, "name": n})
        qg._extract_file = lambda d: ("http://f.zip", "a.zip")
        self.assertTrue(g._handle_media("u1", {}, "m1", ""))
        self.assertEqual(got, {"url": "http://f.zip", "name": "a.zip"})
        # 复原为「无任何富媒体」后才能断言返回 False，否则仍会命中上一步设的文件桩
        qg._extract_file = lambda d: ("", "")
        self.assertFalse(self._gateway()._handle_media("u1", {}, "m1", ""))


class DispatchTextTest(_Base):
    """文本分派：指令与聊天通道必须严格分离。"""

    def test_command_handled(self):
        """斜杠开头且被认领时走指令通道，不投卡片、不回提示。"""
        seen = []
        g = self._gateway(on_command=lambda c, o, m, t: seen.append(t) or True)
        g._reply_unknown = lambda *a: self.fail("不该回提示")
        g._dispatch_text("u1", "/help", "m1")
        self.assertEqual(seen, ["/help"])
        self.assertEqual(self.calls["cards"], [])

    def test_unknown_command_not_sent_to_ai(self):
        """斜杠开头无人认领（含无处理器）时只回提示，绝不投给 AI。"""
        for g in (self._gateway(on_command=lambda *a: False), self._gateway()):
            replied = []
            g._reply_unknown = lambda o, c: replied.append(c)
            g._dispatch_text("u1", "/nosuch", "m1")
            self.assertEqual(replied, ["/nosuch"])
        self.assertEqual(self.calls["cards"], [])

    def test_plain_text_goes_to_card(self):
        """普通消息包装成卡片投出，且来源标记为 qq。"""
        self._gateway()._dispatch_text("u1", "你好", "m1")
        self.assertEqual(len(self.calls["cards"]), 1)
        self.assertEqual(self.calls["cards"][0]["channel"], "qq")


class VoiceFlowTest(_Base):
    """语音链路：开关、线程、暂存顺序与失败提示。"""

    def setUp(self):
        """在父类夹具之外替换配置读取与线程构造。"""
        super().setUp()
        import threading
        from remote_bridge import bridge_store
        self._saved_cfg = bridge_store.get_config
        self._saved_thread = threading.Thread

    def tearDown(self):
        """还原配置读取与线程构造。"""
        from remote_bridge import bridge_store
        import threading
        bridge_store.get_config = self._saved_cfg
        threading.Thread = self._saved_thread
        super().tearDown()

    def _patch_switch(self, on):
        """设置语音识别开关。

        @param on 是否打开
        """
        from remote_bridge import bridge_store
        bridge_store.get_config = lambda: {"push": {"voice": on}}

    def _spy_thread(self):
        """把线程构造替换为只记录不起线程。

        @returns 记录列表
        """
        import threading
        started = []

        class _Spy:
            def __init__(self, target=None, args=(), daemon=None):
                """记录启动参数。"""
                started.append(args)

            def start(self):
                """不执行，只验证起了线程。"""
        threading.Thread = _Spy
        return started

    def test_switch_controls_thread(self):
        """开关关闭时丢弃不起线程；打开时起后台线程，不阻塞回调。"""
        self._patch_switch(False)
        self.assertEqual(self._spy_thread(), [])
        self._gateway()._handle_voice("u1", "http://v.silk", "m1")
        self._patch_switch(True)
        started = self._spy_thread()
        self._gateway()._handle_voice("u1", "http://v.silk", "m1")
        self.assertEqual(started, [("u1", "http://v.silk", "m1")])

    def test_worker_order_and_skip(self):
        """识别成功先暂存再回发（顺序反了用户回 /vo 确认不到内容）；失败则都不做。"""
        order = []
        from remote_bridge import voice_pending
        saved = voice_pending.stash
        voice_pending.stash = lambda o, t, m: order.append("stash")
        try:
            g = self._gateway()
            g._download_and_recognize = lambda o, u: "识别文本"
            g._reply_voice = lambda o, t: order.append("reply")
            g._voice_worker("u1", "http://v.silk", "m1")
            self.assertEqual(order, ["stash", "reply"])
            # 识别失败（空文本）：既不暂存也不回发
            order.clear()
            g._download_and_recognize = lambda o, u: ""
            g._voice_worker("u1", "http://v.silk", "m1")
            self.assertEqual(order, [])
        finally:
            voice_pending.stash = saved

    def test_download_and_recognize_failures(self):
        """下载失败与识别失败各自回发对应提示，且都不返回文本。"""
        replies = []
        g = self._gateway()
        g._reply_voice = lambda o, t: replies.append(t)
        # 下载失败
        qg._download_file = lambda url, path: False
        self.assertEqual(g._download_and_recognize("u1", "http://v.silk"), "")
        self.assertIn("下载失败", replies[-1])
        # 识别失败
        qg._download_file = lambda url, path: True
        from remote_bridge import voice_asr
        saved = voice_asr.voice_file_to_text
        voice_asr.voice_file_to_text = lambda p: ("", "模型缺失")
        try:
            self.assertEqual(g._download_and_recognize("u1", "http://v.silk"), "")
        finally:
            voice_asr.voice_file_to_text = saved
        self.assertIn("识别失败", replies[-1])

    def test_download_and_recognize_success(self):
        """识别成功返回文本，且临时 silk 文件被清理。"""
        seen = {}
        qg._download_file = lambda url, path: (seen.update({"path": path}) or True)
        from remote_bridge import voice_asr
        saved = voice_asr.voice_file_to_text
        voice_asr.voice_file_to_text = lambda p: ("识别结果", "")
        try:
            got = self._gateway()._download_and_recognize("u1", "http://v.silk")
        finally:
            voice_asr.voice_file_to_text = saved
        self.assertEqual(got, "识别结果")
        # 源文件用完即删，不留垃圾
        self.assertFalse(os.path.exists(seen["path"]))


class ImageFlowTest(_Base):
    """图片链路：下载、回收、投卡片。"""

    def test_worker_paths(self):
        """下载失败不投卡片；成功时转 dataURL 并投图片卡片，带上正文。"""
        g = self._gateway()
        g._download_image = lambda o, u: (None, "")
        g._image_worker("u1", "http://i.png", "")
        self.assertEqual(self.calls["images"], [])
        g._download_image = lambda o, u: ("/tmp/a.png", ".png")
        qg._to_data_url = lambda p, e: "data:image/png;base64,AAA"
        g._image_worker("u1", "http://i.png", "配图说明")
        self.assertEqual(len(self.calls["images"]), 1)
        self.assertEqual(self.calls["images"][0]["kw"]["text"], "配图说明")
        # 转 dataURL 失败时也不投
        self.calls["images"].clear()
        qg._to_data_url = lambda p, e: ""
        g._image_worker("u1", "http://i.png", "")
        self.assertEqual(self.calls["images"], [])

    def test_download_image_ext_and_failure(self):
        """按 URL 后缀决定扩展名；下载失败回发提示并返回空。"""
        replies = []
        g = self._gateway()
        g._reply_voice = lambda o, t: replies.append(t)
        qg._download_file = lambda url, path: True
        path, ext = g._download_image("u1", "http://i/photo.JPEG?x=1")
        self.assertEqual(ext, ".jpeg")
        self.assertTrue(path.endswith(".jpeg"))
        # 未知后缀回退 .png
        _, ext2 = g._download_image("u1", "http://i/photo")
        self.assertEqual(ext2, ".png")
        # 下载失败
        qg._download_file = lambda url, path: False
        self.assertEqual(g._download_image("u1", "http://i/a.png"), (None, ""))
        self.assertIn("下载失败", replies[-1])


class ReplyHelpersTest(_Base):
    """回复辅助：无客户端、窗口关闭、发送失败三条分支。"""

    def test_reply_voice_branches(self):
        """无客户端与窗口关闭都不发送；发送失败只记日志不外抛。"""
        self._gateway()._reply_voice("u1", "x")
        saved = qg.message_router.next_seq
        qg.message_router.next_seq = lambda o: (None, 0)
        try:
            self._gateway(client=_SendingClient())._reply_voice("u1", "x")
        finally:
            qg.message_router.next_seq = saved
        self._gateway(client=_SendingClient(ok=False))._reply_voice("u1", "x")

    def test_reply_unknown_branches(self):
        """无客户端与窗口关闭都不发送；正常时回提示并带指令名；失败不外抛。"""
        self._gateway()._reply_unknown("u1", "/x")
        saved = qg.message_router.next_seq
        qg.message_router.next_seq = lambda o: (None, 0)
        try:
            self._gateway(client=_SendingClient())._reply_unknown("u1", "/x")
        finally:
            qg.message_router.next_seq = saved
        client = _SendingClient()
        self._gateway(client=client)._reply_unknown("u1", "/nosuch arg")
        self.assertIn("/nosuch", client.sent[0]["text"])
        self._gateway(client=_SendingClient(ok=False))._reply_unknown("u1", "/x")


class CardPayloadTest(_Base):
    """卡片拼装：语音确认场景必须带 voice 提示。"""

    def test_deliver_text_as_card_flags(self):
        """普通卡片不带语音标记；语音确认卡片带 from_voice 标记与提示。"""
        g = self._gateway()
        g.deliver_text_as_card("u1", "你好", "m1")
        g.deliver_text_as_card("u1", "识别文本", "m2", title="QQ 语音", from_voice=True)
        first, second = self.calls["cards"]
        self.assertFalse(first["kw"]["from_voice"])
        self.assertEqual(first["args"][0], "你好")
        self.assertTrue(second["kw"]["from_voice"])
        self.assertIn("bridge-voice", second["args"][0])

    def test_external_payload_and_voice_hint(self):
        """信封字段齐备；语音提示里同时含 voice 块说明与原文字。"""
        p = qg._external_payload("u1", "正文", "m1", True)
        self.assertEqual(p["type"], "external-call")
        self.assertEqual(p["source"], "qq")
        self.assertEqual(p["page_url"], "")
        self.assertTrue(p["from_voice"])
        self.assertTrue(p["nonce"].startswith("qq-"))
        text = qg._voice_request("今天天气不错")
        self.assertIn("bridge-voice", text)
        self.assertIn("今天天气不错", text)


if __name__ == "__main__":
    unittest.main()
