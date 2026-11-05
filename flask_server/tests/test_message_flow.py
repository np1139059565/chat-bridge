"""推送编排测试（message_flow 执行路径）

背景：
  message_flow 是推送的编排层：决定谁该合成语音、合成顺序、失败如何兜底。
  核心设计是「文字优先」——合成一条语音要一秒以上，若在推文字前做完，
  用户要等整批语音合成完才看到第一条回音。故先推文字、再补语音。

覆盖点：
  1. _collect_pending 的筛选：无 id / 已有路径 / 不该合成 / 无朗读文本
  2. _should_synth 只在 AI 正文上为真，工具结果不合成
  3. _push_voice_results 跳过失败条目、异常不外溢
  4. presynth_voice 只查缓存不合成
  5. 语音开关关闭时全部短路

运行：python -m pytest tests/test_message_flow.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import message_flow as mf


def _ai_msg(mid, voice_text="朗读"):
    """造一条带语音块的 AI 消息。

    @param mid        消息 id
    @param voice_text 朗读文本
    @returns 消息对象
    """
    import json
    return {"id": mid, "role": "assistant", "blocks": [
        {"type": "paragraph", "text": "正文"},
        {"type": "code", "code": json.dumps(
            {"type": "bridge-voice", "text": voice_text}, ensure_ascii=False)},
    ]}


class CollectPendingTest(unittest.TestCase):
    """筛出需要合成的条目。"""

    def setUp(self):
        """固定 _should_synth 为真，隔离筛选逻辑本身。"""
        self._orig = mf._should_synth
        mf._should_synth = lambda m, push: True

    def tearDown(self):
        """还原。"""
        mf._should_synth = self._orig

    def test_picks_message_without_cache(self):
        """没有缓存路径的消息进入待合成列表。"""
        pending = mf._collect_pending([_ai_msg("m1")], {}, {})
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0][0], "m1")

    def test_skips_message_with_cache(self):
        """已有缓存路径的不再合成——避免重复合成同一句话。"""
        pending = mf._collect_pending([_ai_msg("m1")], {}, {"m1": "/a.mp3"})
        self.assertEqual(pending, [])

    def test_skips_message_without_id(self):
        """没有 id 的消息跳过（无法回填路径）。"""
        pending = mf._collect_pending([_ai_msg("")], {}, {})
        self.assertEqual(pending, [])

    def test_skips_when_should_synth_false(self):
        """_should_synth 为假时不合成。"""
        mf._should_synth = lambda m, push: False
        self.assertEqual(mf._collect_pending([_ai_msg("m1")], {}, {}), [])

    def test_skips_when_no_voice_text(self):
        """消息里没有语音朗读文本时跳过。"""
        m = {"id": "m1", "role": "assistant", "blocks": [
            {"type": "paragraph", "text": "只有正文"}]}
        self.assertEqual(mf._collect_pending([m], {}, {}), [])

    def test_multiple_messages_ordered(self):
        """多条消息保持原顺序——顺序决定「文本→语音」的对应关系。"""
        pending = mf._collect_pending(
            [_ai_msg("m1"), _ai_msg("m2")], {}, {})
        self.assertEqual([p[0] for p in pending], ["m1", "m2"])


class ShouldSynthTest(unittest.TestCase):
    """只给 AI 正文合成语音。"""

    def test_ai_text_synthesized(self):
        """普通 AI 正文需要合成。"""
        from remote_bridge import message_router as mr
        orig = mr._should_push
        mr._should_push = lambda m, push: True
        try:
            self.assertTrue(mf._should_synth(_ai_msg("m1"), {}))
        finally:
            mr._should_push = orig

    def test_not_pushed_message_skipped(self):
        """不该推送的消息不合成。"""
        from remote_bridge import message_router as mr
        orig = mr._should_push
        mr._should_push = lambda m, push: False
        try:
            self.assertFalse(mf._should_synth(_ai_msg("m1"), {}))
        finally:
            mr._should_push = orig

    def test_tool_result_not_synthesized(self):
        """工具结果不合成语音——它是数据，不是给人念的内容。"""
        import json
        from remote_bridge import message_router as mr
        orig = mr._should_push
        mr._should_push = lambda m, push: True
        try:
            m = {"id": "t1", "role": "assistant", "blocks": [
                {"type": "code", "code": json.dumps(
                    {"type": "bridge-chat-res", "success": True})}]}
            self.assertFalse(mf._should_synth(m, {}))
        finally:
            mr._should_push = orig


class PushVoiceResultsTest(unittest.TestCase):
    """按合成结果推送语音。"""

    def test_pushes_in_order(self):
        """按原顺序推送，保持文本与语音的对应。"""
        pushed = []
        mf._push_voice_results(None, "u", [("m1", "/a.mp3"), ("m2", "/b.mp3")],
                               push_voice_fn=lambda c, o, p: pushed.append(p))
        self.assertEqual(pushed, ["/a.mp3", "/b.mp3"])

    def test_skips_failed_entries(self):
        """合成失败的条目（空路径）被跳过。"""
        pushed = []
        mf._push_voice_results(None, "u", [("m1", ""), ("m2", "/b.mp3")],
                               push_voice_fn=lambda c, o, p: pushed.append(p))
        self.assertEqual(pushed, ["/b.mp3"])

    def test_push_exception_not_propagated(self):
        """单条推送抛异常不影响后续条目，也不外溢。"""
        pushed = []

        def _fn(client, openid, path):
            if path == "/a.mp3":
                raise RuntimeError("发送失败")
            pushed.append(path)

        mf._push_voice_results(None, "u", [("m1", "/a.mp3"), ("m2", "/b.mp3")],
                               push_voice_fn=_fn)
        self.assertEqual(pushed, ["/b.mp3"])

    def test_empty_results_does_nothing(self):
        """空结果列表不调推送。"""
        pushed = []
        mf._push_voice_results(None, "u", [], push_voice_fn=lambda *a: pushed.append(1))
        self.assertEqual(pushed, [])


class PresynthVoiceTest(unittest.TestCase):
    """预合成：只查缓存，不合成。"""

    def setUp(self):
        """替换缓存查询与合成判断。"""
        from remote_bridge import voice_cache
        self._orig_lookup = voice_cache.lookup
        self._orig_should = mf._should_synth
        mf._should_synth = lambda m, push: True

    def tearDown(self):
        """还原。"""
        from remote_bridge import voice_cache
        voice_cache.lookup = self._orig_lookup
        mf._should_synth = self._orig_should

    def test_returns_cached_only(self):
        """只有缓存命中的返回，未命中的不合成。"""
        from remote_bridge import voice_cache
        voice_cache.lookup = lambda text: "/cached.mp3" if text == "有缓存" else ""
        out = mf.presynth_voice([_ai_msg("m1", "有缓存"), _ai_msg("m2", "无缓存")],
                                {"voice": True})
        self.assertEqual(out, {"m1": "/cached.mp3"})

    def test_voice_off_returns_empty(self):
        """语音开关关闭时直接返回空字典，不查缓存。"""
        from remote_bridge import voice_cache
        called = []
        voice_cache.lookup = lambda text: called.append(text) or ""
        out = mf.presynth_voice([_ai_msg("m1")], {"voice": False})
        self.assertEqual(out, {})
        self.assertEqual(called, [])

    def test_skips_unneeded_message(self):
        """不该合成的消息不查缓存。"""
        from remote_bridge import voice_cache
        called = []
        mf._should_synth = lambda m, push: False
        voice_cache.lookup = lambda text: called.append(text) or ""
        out = mf.presynth_voice([_ai_msg("m1")], {"voice": True})
        self.assertEqual(out, {})
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
