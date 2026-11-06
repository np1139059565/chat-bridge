"""语音识别测试（voice_asr 执行路径）

背景：
  该模块此前零覆盖。QQ 语音消息能否转成文字全靠它，
  失败时用户只会收到「识别失败」或干脆没动静。
  且 pilk、vosk 都是可选依赖，缺依赖的分支若写错，
  会让整条语音链路在无提示的情况下断掉。

覆盖点：
  1. 可选依赖导入：缺失返回 None，存在返回模块
  2. 模型目录解析：环境变量优先，目录不存在时退回约定路径
  3. WAV 封装：单声道 / 16bit / 采样率 / 帧数
  4. 线性重采样：同采样率直通、空输入、升降采样点数、常量信号
  5. SILK 解码：缺 pilk 与解码异常都返回说明；成功时产出 WAV 并清临时文件
  6. vosk 识别：缺依赖、模型目录缺失、模型加载异常、成功、采样率不符时重采样
  7. 对外主入口：解码失败短路、成功后删中间 WAV

写法说明：
  断言雷同的用例合并到同一方法内，分段注释说明各自验证什么。

运行：python -m pytest tests/test_voice_asr.py -q
"""
import json
import os
import struct
import sys
import tempfile
import unittest
import wave
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import voice_asr as asr


class _FakePilk:
    """模拟 pilk：把预设 PCM 写进解码输出文件。"""

    def __init__(self, pcm=b"\x00\x01" * 100, raise_on_decode=False):
        self._pcm = pcm
        self._raise = raise_on_decode
        self.seen_rate = None

    def SilkDecoder(self, pcm_rate=24000):
        """返回解码器实例，记录采样率便于断言。"""
        self.seen_rate = pcm_rate
        outer = self

        class _Dec:
            def decode(self, src, dst):
                """按配置写入 PCM 或抛异常。"""
                if outer._raise:
                    raise RuntimeError("解码崩了")
                with open(dst, "wb") as f:
                    f.write(outer._pcm)
        return _Dec()


class _FakeVosk:
    """模拟 vosk：返回预设识别文本，可配置模型加载失败。"""

    def __init__(self, text="你好", raise_on_model=False):
        self._text = text
        self._raise = raise_on_model
        self.rec_rate = None
        outer = self

        class _Model:
            def __init__(self, path):
                """模拟模型加载，可配置为失败。"""
                if outer._raise:
                    raise RuntimeError("模型加载失败")

        def _recognizer(model, rate):
            """返回识别器，FinalResult 输出预设文本。"""
            self.rec_rate = rate

            class _Rec:
                def AcceptWaveform(self, raw):
                    """吞掉音频数据。"""
                    return True

                def FinalResult(self):
                    """返回带 text 字段的 JSON 字符串。"""
                    return json.dumps({"text": outer._text})
            return _Rec()

        self.Model = _Model
        self.KaldiRecognizer = _recognizer


def _with_module(name, module):
    """上下文式的 sys.modules 替换，退出时还原。

    _ensure_import 走的是 __import__，只能通过 sys.modules 注入假模块。
    @param name 模块名
    @param module 假模块对象（传 None 表示模块不可用）
    """
    class _Ctx:
        def __enter__(self):
            self.saved = sys.modules.get(name)
            self.existed = name in sys.modules
            sys.modules[name] = module

        def __exit__(self, *a):
            if self.existed:
                sys.modules[name] = self.saved
            else:
                sys.modules.pop(name, None)
            return False
    return _Ctx()


class DependencyTest(unittest.TestCase):
    """可选依赖导入与模型目录解析。"""

    def setUp(self):
        """保存原环境变量，用例结束还原。"""
        self._old = os.environ.get("VOSK_MODEL_PATH")

    def tearDown(self):
        """还原环境变量。"""
        if self._old is None:
            os.environ.pop("VOSK_MODEL_PATH", None)
        else:
            os.environ["VOSK_MODEL_PATH"] = self._old

    def test_import_cases(self):
        """缺失模块返回 None；存在则返回模块本身。"""
        self.assertIsNone(asr._ensure_import("definitely_not_a_module_xyz"))
        self.assertIs(asr._ensure_import("json"), json)

    def test_model_path_priority(self):
        """环境变量指向真实目录时优先；目录不存在时退回工程约定路径。"""
        d = tempfile.mkdtemp()
        try:
            os.environ["VOSK_MODEL_PATH"] = d
            self.assertEqual(asr._default_model_path(), d)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        os.environ["VOSK_MODEL_PATH"] = os.path.join(tempfile.gettempdir(), "no_such_dir_xyz")
        self.assertIn("vosk-model-cn", asr._default_model_path())


class WaveIoTest(unittest.TestCase):
    """WAV 封装与重采样：头信息错了 vosk 就读不出音频。"""

    def setUp(self):
        """独立临时目录。"""
        self._dir = tempfile.mkdtemp()
        self._path = os.path.join(self._dir, "o.wav")

    def tearDown(self):
        """清理。"""
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_write_wav_header(self):
        """单声道、16bit、采样率与帧数都写入正确。"""
        pcm = struct.pack("<5h", 1, 2, 3, 4, 5)
        asr._write_wav(self._path, pcm, 24000)
        with wave.open(self._path, "rb") as w:
            self.assertEqual(w.getnchannels(), 1)
            self.assertEqual(w.getsampwidth(), 2)
            self.assertEqual(w.getframerate(), 24000)
            self.assertEqual(w.getnframes(), 5)
            self.assertEqual(w.readframes(5), pcm)

    def test_resample_cases(self):
        """同采样率直通、空输入返回空、升降采样点数、常量信号不失真。"""
        # 同采样率：不做无谓运算
        pcm = struct.pack("<3h", 10, 20, 30)
        self.assertEqual(asr._resample_int16(pcm, 16000, 16000), pcm)
        # 空输入
        self.assertEqual(asr._resample_int16(b"", 24000, 16000), b"")
        # 降采样：点数约为原来三分之二
        n = 3000
        down = asr._resample_int16(struct.pack("<%dh" % n, *([100] * n)), 24000, 16000)
        self.assertEqual(len(down) // 2, int(n * 16000 / 24000))
        # 升采样：点数翻倍
        up = asr._resample_int16(struct.pack("<100h", *([50] * 100)), 8000, 16000)
        self.assertEqual(len(up) // 2, 200)
        # 常量信号：插值不应引入畸变
        out = asr._resample_int16(struct.pack("<300h", *([500] * 300)), 24000, 16000)
        vals = struct.unpack("<%dh" % (len(out) // 2), out)
        self.assertTrue(all(abs(v - 500) <= 1 for v in vals))


class SilkToWavTest(unittest.TestCase):
    """SILK 解码：依赖缺失与解码异常都必须返回说明。"""

    def setUp(self):
        """独立临时目录。"""
        self._dir = tempfile.mkdtemp()
        self._wav = os.path.join(self._dir, "o.wav")

    def tearDown(self):
        """清理。"""
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_failure_paths(self):
        """未装 pilk 与解码抛异常，都返回带 pilk 字样的说明，不穿透异常。"""
        with _with_module("pilk", None):
            ok, err = asr.silk_to_wav("x.silk", self._wav)
        self.assertFalse(ok)
        self.assertIn("pilk", err)
        with _with_module("pilk", _FakePilk(raise_on_decode=True)):
            ok, err = asr.silk_to_wav("x.silk", self._wav)
        self.assertFalse(ok)
        self.assertIn("pilk", err)

    def test_decode_success(self):
        """解码成功：产出可读 WAV，默认采样率 24000，临时 PCM 用完即删。"""
        fake = _FakePilk()
        with _with_module("pilk", fake):
            ok, err = asr.silk_to_wav("x.silk", self._wav)
        self.assertTrue(ok, err)
        self.assertEqual(fake.seen_rate, 24000)
        with wave.open(self._wav, "rb") as w:
            self.assertGreater(w.getnframes(), 0)
        self.assertFalse(os.path.exists(self._wav + ".pcm"))


class WavToTextTest(unittest.TestCase):
    """vosk 识别：缺依赖、模型缺失、加载异常、成功、采样率不符。"""

    def setUp(self):
        """造一个真实的 16k WAV 文件。"""
        self._dir = tempfile.mkdtemp()
        self._wav = os.path.join(self._dir, "i.wav")
        asr._write_wav(self._wav, struct.pack("<100h", *([10] * 100)), 16000)

    def tearDown(self):
        """清理。"""
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_dependency_and_model_failures(self):
        """未装 vosk 返回说明；模型目录缺失提示怎么配；模型加载异常转说明。"""
        with _with_module("vosk", None):
            text, err = asr.wav_to_text(self._wav)
        self.assertEqual(text, "")
        self.assertIn("vosk", err)
        with _with_module("vosk", _FakeVosk()):
            text, err = asr.wav_to_text(self._wav, model_path=os.path.join(self._dir, "nodir"))
        self.assertEqual(text, "")
        self.assertIn("VOSK_MODEL_PATH", err)
        with _with_module("vosk", _FakeVosk(raise_on_model=True)):
            text, err = asr.wav_to_text(self._wav, model_path=self._dir)
        self.assertEqual(text, "")
        self.assertIn("vosk", err)

    def test_success_and_resample(self):
        """识别成功返回文字；源采样率 24k 时喂给识别器的必须是 16k。"""
        fake = _FakeVosk(text="今天天气不错")
        with _with_module("vosk", fake):
            text, err = asr.wav_to_text(self._wav, model_path=self._dir)
        self.assertEqual(err, "")
        self.assertEqual(text, "今天天气不错")
        self.assertEqual(fake.rec_rate, asr.VOSK_RATE)
        # 采样率不符：先重采样再识别
        wav24 = os.path.join(self._dir, "i24.wav")
        asr._write_wav(wav24, struct.pack("<240h", *([5] * 240)), 24000)
        fake = _FakeVosk()
        with _with_module("vosk", fake):
            asr.wav_to_text(wav24, model_path=self._dir)
        self.assertEqual(fake.rec_rate, asr.VOSK_RATE)


class VoiceFileToTextTest(unittest.TestCase):
    """对外主入口：串起解码与识别，并保证中间产物被清理。"""

    def setUp(self):
        """独立临时目录并保存原函数。"""
        self._dir = tempfile.mkdtemp()
        self._orig = asr.wav_to_text

    def tearDown(self):
        """还原被替换的函数并清理。"""
        asr.wav_to_text = self._orig
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_decode_failure_skips_recognition(self):
        """解码失败时直接返回错误，不进入识别环节。"""
        called = {"n": 0}

        def _should_not_call(*a, **k):
            """识别若被调用即计数，用于断言没被调用。"""
            called["n"] += 1
            return "", ""

        asr.wav_to_text = _should_not_call
        with _with_module("pilk", None):
            text, err = asr.voice_file_to_text("x.silk")
        self.assertEqual(text, "")
        self.assertIn("pilk", err)
        self.assertEqual(called["n"], 0)

    def test_success_cleans_intermediate_wav(self):
        """成功后中间 WAV 必须删除，否则语音目录会越积越多。"""
        seen = {}

        def _fake_recognize(wav_path, model_path=None):
            """记录中间 WAV 路径与存在性，返回文本。"""
            seen["wav"] = wav_path
            seen["existed"] = os.path.exists(wav_path)
            return "识别结果", ""

        asr.wav_to_text = _fake_recognize
        with _with_module("pilk", _FakePilk()):
            text, err = asr.voice_file_to_text("x.silk")
        self.assertEqual(err, "")
        self.assertEqual(text, "识别结果")
        # 识别时 WAV 确实存在，识别后被删除
        self.assertTrue(seen["existed"])
        self.assertFalse(os.path.exists(seen["wav"]))


if __name__ == "__main__":
    unittest.main()
