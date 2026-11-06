# 真实执行层测试：语音合成的分发、降级、清理与并发闸门
#
# 背景：test_voice_engine.py 里 4 处用例把 _dispatch 整个替换成假函数，
# 只验证了「按顺序试了哪些引擎」，而真正跑在线上的是 _dispatch 内部的路由、
# text_to_voice 的降级循环、失败后清理半成品、以及信号量的获取与释放——
# 这些此前一行都没被测到。历史上就因这类假覆盖漏掉过「返回值解包错误
# 导致合成 100% 失败」的故障。
#
# 本文件的取舍：只替换最底层的音频生成（_synth_piper 等叶子函数，
# 它们依赖外部可执行文件，无法在单测里确定性地产出音频），
# 其余全部走真实代码：
#   · _dispatch 的真实路由
#   · text_to_voice 的真实降级循环与错误汇总
#   · 失败后的半成品清理
#   · 并发信号量的获取与释放
# 另有一个真实 SAPI 冒烟用例：在 Windows 上真跑一次合成，验证端到端可用。
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import voice_tts


class VoiceExecutionTestCase(unittest.TestCase):
    """分发与降级的真实执行路径测试。"""

    def setUp(self):
        """保存原始配置函数与叶子实现，准备临时目录。"""
        self._orig_cfg = voice_tts._load_voice_cfg
        self._orig_piper = voice_tts._synth_piper
        self._orig_pyttsx3 = voice_tts._synth_pyttsx3
        self._tmpdir = tempfile.mkdtemp(prefix="tts_exec_")

    def tearDown(self):
        """还原所有被替换的函数，清理临时目录。"""
        voice_tts._load_voice_cfg = self._orig_cfg
        voice_tts._synth_piper = self._orig_piper
        voice_tts._synth_pyttsx3 = self._orig_pyttsx3
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _out(self, name="out.mp3"):
        """拼一个临时输出路径。"""
        return os.path.join(self._tmpdir, name)

    def _cfg(self, **kw):
        """构造配置并把读取函数替换成返回它。"""
        cfg = dict(kw)
        voice_tts._load_voice_cfg = lambda: cfg
        return cfg

    # ---------- 分发路由 ----------

    def test_dispatch_routes_piper_to_real_impl(self):
        """engine=piper 时路由到 _synth_piper，且参数原样传入。"""
        calls = []

        def fake_piper(text, out_path, cfg):
            calls.append((text, out_path, cfg))
            return True, ""

        voice_tts._synth_piper = fake_piper
        cfg = {"voice_engine": "piper"}
        ok, err = voice_tts._dispatch("piper", "你好", self._out(), None, cfg)
        self.assertTrue(ok)
        self.assertEqual(err, "")
        # 确认真的走到了 piper 实现，而不是别处
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "你好")
        self.assertIs(calls[0][2], cfg)

    def test_dispatch_unknown_engine_reports_name(self):
        """未知引擎返回失败，且错误里带引擎名，便于排查。"""
        ok, err = voice_tts._dispatch("nosuch", "你好", self._out(), None, {})
        self.assertFalse(ok)
        self.assertIn("nosuch", err)

    # ---------- 降级循环 ----------

    def test_fallback_succeeds_on_second_engine(self):
        """第一个引擎失败后继续试下一个，成功即返回。"""
        def fail_piper(text, out_path, cfg):
            return False, "piper 挂了"

        def ok_pyttsx3(text, out_path, cfg):
            # 真实实现会产出文件，这里也产出，模拟成功路径
            with open(out_path, "wb") as f:
                f.write(b"fake-mp3")
            return True, ""

        voice_tts._synth_piper = fail_piper
        voice_tts._synth_pyttsx3 = ok_pyttsx3
        self._cfg(voice_engine="auto", voice_fallback="piper,pyttsx3")

        out = self._out()
        ok, err = voice_tts.text_to_voice("测试", out)
        self.assertTrue(ok)
        self.assertEqual(err, "")
        # 产物应留在磁盘上
        self.assertTrue(os.path.exists(out))

    def test_all_engines_fail_aggregates_each_error(self):
        """全部失败时，错误串逐个列出引擎名与原因。"""
        voice_tts._synth_piper = lambda t, o, c: (False, "piper 原因")
        voice_tts._synth_pyttsx3 = lambda t, o, c: (False, "pyttsx3 原因")
        self._cfg(voice_engine="auto", voice_fallback="piper,pyttsx3")

        ok, err = voice_tts.text_to_voice("测试", self._out())
        self.assertFalse(ok)
        # 每个引擎都应在错误串里留痕，否则排查时不知谁失败过
        self.assertIn("[piper] piper 原因", err)
        self.assertIn("[pyttsx3] pyttsx3 原因", err)

    # ---------- 失败后的清理 ----------

    def test_partial_output_removed_when_engine_fails(self):
        """引擎写了半成品后失败，该文件必须被清掉。"""
        def dirty_piper(text, out_path, cfg):
            # 模拟「写了点东西然后失败」：残留不清会让下次误判为已生成
            with open(out_path, "wb") as f:
                f.write(b"half")
            return False, "中途失败"

        voice_tts._synth_piper = dirty_piper
        self._cfg(voice_engine="piper")  # 固定引擎：失败后不再降级，直接收尾

        out = self._out()
        ok, _ = voice_tts.text_to_voice("测试", out)
        self.assertFalse(ok)
        # 半成品必须已被删除
        self.assertFalse(os.path.exists(out))

    # ---------- 并发闸门 ----------

    def test_semaphore_released_after_failure(self):
        """失败路径也必须释放信号量，否则连失败几次后整条链路会堵死。"""
        voice_tts._synth_piper = lambda t, o, c: (False, "故意失败")
        self._cfg(voice_engine="piper")

        # 连续失败两次：若第一次没释放名额，第二次会卡在获取处直到超时
        for _ in range(2):
            ok, err = voice_tts.text_to_voice("测试", self._out())
            self.assertFalse(ok)
            self.assertNotIn("闸门等待超时", err)

    def test_empty_text_returns_before_touching_engine(self):
        """空文本直接返回失败，不进入任何引擎——避免无谓的子进程开销。"""
        called = []
        voice_tts._synth_piper = lambda t, o, c: called.append(1) or (True, "")
        self._cfg(voice_engine="piper")

        ok, err = voice_tts.text_to_voice("   ", self._out())
        self.assertFalse(ok)
        self.assertEqual(called, [])  # 引擎一次都不该被调用


@unittest.skipUnless(os.name == "nt", "SAPI 仅在 Windows 上可用")
class VoiceSapiSmokeTestCase(unittest.TestCase):
    """真实端到端冒烟：用系统自带 SAPI 真合成一次。

    这是唯一一个真正跑通「文本 → 音频文件」全链路的用例。
    其余用例为了确定性替换了叶子函数，而本用例不做任何替换，
    因此能发现「参数解包错、产物没落盘、编码失败」这类只有真实执行才暴露的问题。
    """

    def test_synthesize_real_audio(self):
        """真合成一句短文本，断言产出了非空 MP3。"""
        tmpdir = tempfile.mkdtemp(prefix="tts_sapi_")
        try:
            out = os.path.join(tmpdir, "out.mp3")
            ok, err = voice_tts._dispatch("sapi", "测试", out, None, {})
            self.assertTrue(ok, "SAPI 合成失败：%s" % err)
            # 产物必须存在且非空，否则等于「返回成功但没东西」
            self.assertTrue(os.path.exists(out))
            self.assertGreater(os.path.getsize(out), 0)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
