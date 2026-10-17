"""语音合成多引擎切换测试

覆盖点：
- 配置解析：固定引擎只返回一个，auto 按 fallback 顺序展开
- 引擎分发：未知引擎给出明确错误，不抛异常
- 降级行为：auto 模式下前一个引擎失败后继续尝试下一个
- 不降级行为：固定引擎失败后立即返回，不再尝试其它引擎
- 音频编码：WAV 转 MP3 产出合法文件头
- 空文本：直接返回失败，不触碰任何引擎

所有用例都替换掉 _load_voice_cfg，不读写真实配置文件，也不联网。
"""
import os
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import voice_tts
from remote_bridge import voice_mp3


class VoiceEngineTestCase(unittest.TestCase):
    """引擎切换相关的单元测试。"""

    def setUp(self):
        """每个用例前保存原始配置函数，便于用例结束后还原。"""
        self._orig_cfg = voice_tts._load_voice_cfg
        self._tmpdir = tempfile.mkdtemp(prefix="tts_test_")

    def tearDown(self):
        """还原配置函数，并清理临时目录。"""
        voice_tts._load_voice_cfg = self._orig_cfg
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _out(self, name="out.mp3"):
        """拼一个临时输出路径。

        @param name 文件名
        @returns 绝对路径
        """
        return os.path.join(self._tmpdir, name)

    def _stub_cfg(self, cfg):
        """把配置读取替换成返回固定字典。

        @param cfg 配置字典
        """
        voice_tts._load_voice_cfg = lambda: cfg

    # ---------- 配置解析 ----------

    def test_fixed_engine_returns_single(self):
        """固定引擎名时，尝试列表只含该引擎。"""
        order = voice_tts._engine_order({"voice_engine": "piper"})
        self.assertEqual(order, ["piper"])

    def test_auto_engine_follows_fallback(self):
        """auto 模式按 fallback 的逗号分隔顺序展开。"""
        order = voice_tts._engine_order({
            "voice_engine": "auto",
            "voice_fallback": "pyttsx3, edge_tts",
        })
        self.assertEqual(order, ["pyttsx3", "edge_tts"])

    def test_auto_engine_blank_fallback_uses_default(self):
        """auto 模式未配 fallback 时用内置默认顺序。"""
        order = voice_tts._engine_order({"voice_engine": "auto"})
        self.assertEqual(order, ["piper", "pyttsx3", "edge_tts"])

    def test_missing_engine_key_defaults_to_auto(self):
        """配置缺 voice_engine 时按 auto 处理。"""
        order = voice_tts._engine_order({})
        self.assertEqual(order, ["piper", "pyttsx3", "edge_tts"])

    # ---------- 引擎分发 ----------

    def test_unknown_engine_returns_error(self):
        """未知引擎名返回明确错误，不抛异常。"""
        ok, err = voice_tts._dispatch("nosuch", "文本", self._out(), None, {})
        self.assertFalse(ok)
        self.assertIn("未知语音引擎", err)

    def test_empty_text_returns_error(self):
        """空文本直接失败，不进入任何引擎。"""
        self._stub_cfg({"voice_engine": "edge_tts"})
        ok, err = voice_tts.text_to_voice("   ", self._out())
        self.assertFalse(ok)
        self.assertIn("为空", err)

    # ---------- 降级与不降级 ----------

    def test_auto_falls_through_to_next_engine(self):
        """auto 模式下前一个引擎失败，继续尝试下一个并成功。"""
        calls = []

        def _fake_dispatch(engine, text, out_path, voice, cfg):
            """记录被调用的引擎；第一个失败，第二个成功。"""
            calls.append(engine)
            if engine == "first":
                return False, "模拟失败"
            with open(out_path, "wb") as fh:
                fh.write(b"fake-audio")
            return True, ""

        orig = voice_tts._dispatch
        voice_tts._dispatch = _fake_dispatch
        try:
            self._stub_cfg({"voice_engine": "auto", "voice_fallback": "first,second"})
            ok, err = voice_tts.text_to_voice("测试", self._out())
        finally:
            voice_tts._dispatch = orig

        self.assertTrue(ok, err)
        self.assertEqual(calls, ["first", "second"])

    def test_fixed_engine_does_not_fall_through(self):
        """固定引擎失败后立即返回，不再尝试其它引擎。"""
        calls = []

        def _fake_dispatch(engine, text, out_path, voice, cfg):
            """记录调用并一律返回失败。"""
            calls.append(engine)
            return False, "模拟失败"

        orig = voice_tts._dispatch
        voice_tts._dispatch = _fake_dispatch
        try:
            self._stub_cfg({"voice_engine": "piper", "voice_fallback": "piper,pyttsx3"})
            ok, err = voice_tts.text_to_voice("测试", self._out())
        finally:
            voice_tts._dispatch = orig

        self.assertFalse(ok)
        self.assertEqual(calls, ["piper"])
        self.assertIn("piper", err)

    def test_all_engines_fail_reports_each(self):
        """全部引擎失败时，错误信息包含每个引擎的原因。"""
        def _fake_dispatch(engine, text, out_path, voice, cfg):
            """一律失败，错误信息带引擎名。"""
            return False, "原因-%s" % engine

        orig = voice_tts._dispatch
        voice_tts._dispatch = _fake_dispatch
        try:
            self._stub_cfg({"voice_engine": "auto", "voice_fallback": "a,b"})
            ok, err = voice_tts.text_to_voice("测试", self._out())
        finally:
            voice_tts._dispatch = orig

        self.assertFalse(ok)
        self.assertIn("原因-a", err)
        self.assertIn("原因-b", err)

    def test_failed_engine_cleans_partial_output(self):
        """引擎失败后清掉残留的半成品文件。"""
        out = self._out()

        def _fake_dispatch(engine, text, out_path, voice, cfg):
            """写入半个文件后返回失败。"""
            with open(out_path, "wb") as fh:
                fh.write(b"partial")
            return False, "模拟失败"

        orig = voice_tts._dispatch
        voice_tts._dispatch = _fake_dispatch
        try:
            self._stub_cfg({"voice_engine": "auto", "voice_fallback": "a"})
            voice_tts.text_to_voice("测试", out)
        finally:
            voice_tts._dispatch = orig

        self.assertFalse(os.path.exists(out))

    # ---------- 音频编码 ----------

    def test_wav_to_mp3_produces_valid_header(self):
        """WAV 输入编码后得到带合法帧同步头的 MP3。"""
        wav_path = self._out("src.wav")
        mp3_path = self._out("dst.mp3")
        # 造一段 22050Hz 单声道 16 位静音 WAV，长度约 0.2 秒
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(b"\x00\x00" * 4410)

        ok, err = voice_mp3.ensure_mp3(wav_path, mp3_path)
        self.assertTrue(ok, err)
        self.assertTrue(os.path.exists(mp3_path))
        self.assertGreater(os.path.getsize(mp3_path), 0)
        with open(mp3_path, "rb") as fh:
            head = fh.read(2)
        # MPEG 帧同步：高 11 位全为 1
        self.assertEqual(head[0], 0xFF)
        self.assertEqual(head[1] & 0xE0, 0xE0)

    def test_nonstandard_rate_is_resampled(self):
        """非标准采样率（如 96000）能重采样后正常编码。"""
        wav_path = self._out("src96k.wav")
        mp3_path = self._out("dst96k.mp3")
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(96000)
            wf.writeframes(b"\x00\x00" * 9600)

        ok, err = voice_mp3.ensure_mp3(wav_path, mp3_path)
        self.assertTrue(ok, err)
        self.assertGreater(os.path.getsize(mp3_path), 0)

    def test_mp3_input_is_moved_not_reencoded(self):
        """源已是 MP3 时直接搬到目标位置，内容不变。"""
        src = self._out("already.mp3")
        dst = self._out("moved.mp3")
        payload = b"\xff\xfb\x90\x00fake-mp3-payload"
        with open(src, "wb") as fh:
            fh.write(payload)

        ok, err = voice_mp3.ensure_mp3(src, dst)
        self.assertTrue(ok, err)
        self.assertFalse(os.path.exists(src))
        with open(dst, "rb") as fh:
            self.assertEqual(fh.read(), payload)


if __name__ == "__main__":
    unittest.main()
