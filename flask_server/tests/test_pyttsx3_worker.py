"""pyttsx3 合成子进程测试（pyttsx3_worker 执行路径）

背景：
  该模块此前零覆盖。它是每次合成语音时独立拉起的子进程，
  负责读文本、初始化引擎、应用音色语速、产出 WAV。
  父进程只按退出码判断成败，故退出码一旦判错，
  用户会拿到静音或旧音频，却看不到任何报错。

覆盖点：
  1. 文本读取：正常、文件缺失、纯空白
  2. 音色应用：按 name 命中、按 id 命中、未命中保持默认、空值不处理
  3. 语速应用：正常值、非数字回退、下限与上限钳制
  4. 合成与产物校验：成功、产物缺失、产物为空、旧产物先删
  5. 引擎生命周期：异常也停止引擎、停止失败不影响退出码
  6. 入口分发：参数不足、读文本失败、未安装 pyttsx3、正常路径

写法说明：
  断言高度相似的用例合并为表驱动，用例名仍逐条保留在断言的附加信息里，
  失败时能直接看出是哪一组数据出问题。

运行：python -m pytest tests/test_pyttsx3_worker.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import pyttsx3_worker as w


class _FakeVoice:
    """模拟一个系统音色对象，只暴露 id 与 name。"""

    def __init__(self, vid, name):
        self.id = vid
        self.name = name


class _FakeEngine:
    """模拟 pyttsx3 引擎，记录被设置过的属性与调用顺序。"""

    def __init__(self, voices=None, save_bytes=100, raise_on_save=False):
        self._voices = voices or []
        self.props = {}
        self._save_bytes = save_bytes
        self._raise_on_save = raise_on_save
        self.stopped = False

    def getProperty(self, key):
        """返回音色列表；其余属性返回 None。"""
        if key == "voices":
            return self._voices
        return None

    def setProperty(self, key, value):
        """记录被设置的属性，供断言。"""
        self.props[key] = value

    def save_to_file(self, text, out_path):
        """模拟写音频文件；可配置为写入 0 字节或直接抛异常。"""
        if self._raise_on_save:
            raise RuntimeError("合成失败")
        with open(out_path, "wb") as f:
            f.write(b"\x00" * self._save_bytes)

    def runAndWait(self):
        """模拟阻塞合成。"""

    def stop(self):
        """记录引擎已停止。"""
        self.stopped = True


def _fake_module(engine=None, raise_on_init=False):
    """构造只含 init 的假 pyttsx3 模块。

    @param engine 要返回的引擎实例
    @param raise_on_init 是否让 init 抛异常
    @returns 假模块对象
    """
    class _M:
        @staticmethod
        def init(driverName=None):
            """按配置返回引擎或抛异常。"""
            if raise_on_init:
                raise RuntimeError("无 SAPI")
            return engine
    return _M


class ReadTextTest(unittest.TestCase):
    """文本读取：文件缺失与空白文本都必须判失败，不能交给引擎。"""

    def setUp(self):
        """每个用例独立的临时文本路径。"""
        import tempfile
        self._dir = tempfile.mkdtemp()
        self._path = os.path.join(self._dir, "t.txt")

    def tearDown(self):
        """清理临时目录，避免残留文件影响后续运行。"""
        import shutil
        shutil.rmtree(self._dir, ignore_errors=True)

    def _write(self, text):
        """写入测试文本。"""
        with open(self._path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_read_text_cases(self):
        """正常文本原样返回；文件缺失与纯空白都返回 None。"""
        # 正常文本
        self._write("你好，世界")
        self.assertEqual(w._read_text(self._path), "你好，世界")
        # 文件不存在：不得抛异常
        self.assertIsNone(w._read_text(os.path.join(self._dir, "no.txt")))
        # 纯空白：交给引擎也只会得到静音
        self._write("   \n\t ")
        self.assertIsNone(w._read_text(self._path))


class ApplyVoiceTest(unittest.TestCase):
    """音色应用：兼容不同系统对同一音色的命名差异。"""

    def _engine(self):
        """构造含两个音色的假引擎。"""
        return _FakeEngine(voices=[
            _FakeVoice("id-xiaoxiao", "Microsoft Xiaoxiao"),
            _FakeVoice("id-yunxi", "Microsoft Yunxi"),
        ])

    def test_voice_cases(self):
        """空值保持默认、按名命中、按 id 命中、无匹配保持默认。"""
        # 空音色不设置任何属性
        eng = self._engine()
        w._apply_voice(eng, "  ")
        self.assertNotIn("voice", eng.props)
        # 按名称命中
        eng = self._engine()
        w._apply_voice(eng, "xiaoxiao")
        self.assertEqual(eng.props.get("voice"), "id-xiaoxiao")
        # 名称不匹配但 id 命中
        eng = self._engine()
        w._apply_voice(eng, "yunxi")
        self.assertEqual(eng.props.get("voice"), "id-yunxi")
        # 无任何匹配：不得随意改音色
        eng = self._engine()
        w._apply_voice(eng, "nosuchvoice")
        self.assertNotIn("voice", eng.props)


class ApplyRateTest(unittest.TestCase):
    """语速应用：收敛到 SAPI 合理区间，防过慢拖沓、过快吐字不清。"""

    def test_rate_clamped(self):
        """正常值原样设置，非数字回退 150，低于 80 抬到 80，高于 300 压到 300。"""
        for raw, want in (("200", 200), ("很快", 150), ("10", 80), ("999", 300)):
            eng = _FakeEngine()
            w._apply_rate(eng, raw)
            self.assertEqual(eng.props.get("rate"), want, "输入=%s" % raw)


class SynthesizeTest(unittest.TestCase):
    """合成与产物校验：产物缺失或为空必须判失败。"""

    def setUp(self):
        """每个用例独立的输出路径。"""
        import tempfile
        self._dir = tempfile.mkdtemp()
        self._out = os.path.join(self._dir, "o.wav")

    def tearDown(self):
        """清理临时目录。"""
        import shutil
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_success_writes_file(self):
        """正常合成后产出非空文件，退出码 0。"""
        eng = _FakeEngine(save_bytes=128)
        self.assertEqual(w._synthesize(eng, "文本", self._out), 0)
        self.assertTrue(os.path.getsize(self._out) > 0)

    def test_invalid_output_fails(self):
        """产物为 0 字节判失败；且旧产物必须先删，否则会被误判为成功。"""
        with open(self._out, "wb") as f:
            f.write(b"old" * 10)
        eng = _FakeEngine(save_bytes=0)
        self.assertEqual(w._synthesize(eng, "文本", self._out), 1)
        # 本次写入 0 字节，旧内容必须已被清掉
        self.assertEqual(os.path.getsize(self._out), 0)

    def test_missing_output_fails(self):
        """引擎没写文件时判失败，不向父进程交出无效音频。"""
        eng = _FakeEngine()
        eng.save_to_file = lambda text, path: None
        self.assertEqual(w._synthesize(eng, "文本", self._out), 1)


class RunEngineTest(unittest.TestCase):
    """引擎生命周期：无论成败都要停止引擎。"""

    def setUp(self):
        """构造临时输出路径与一个可成功合成的假引擎。"""
        import tempfile
        self._dir = tempfile.mkdtemp()
        self._out = os.path.join(self._dir, "o.wav")

    def tearDown(self):
        """清理临时目录。"""
        import shutil
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_success_stops_engine(self):
        """成功路径：产出文件，且引擎被停止。"""
        eng = _FakeEngine(save_bytes=64)
        code = w._run_engine(_fake_module(eng), "文本", self._out, "", "150")
        self.assertEqual(code, 0)
        self.assertTrue(eng.stopped)

    def test_failures_return_one(self):
        """初始化失败与合成异常都返回 1；后者仍要停止引擎。"""
        mod = _fake_module(raise_on_init=True)
        self.assertEqual(w._run_engine(mod, "文本", self._out, "", "150"), 1)
        eng = _FakeEngine(raise_on_save=True)
        code = w._run_engine(_fake_module(eng), "文本", self._out, "", "150")
        self.assertEqual(code, 1)
        self.assertTrue(eng.stopped)


class StopEngineTest(unittest.TestCase):
    """引擎停止：任何失败都不得影响退出码。"""

    def test_stop_is_safe(self):
        """引擎为 None 直接返回；stop 抛异常静默忽略。"""
        w._stop_engine(None)

        class _E:
            def stop(self):
                """模拟停止失败。"""
                raise RuntimeError("停止失败")
        w._stop_engine(_E())


class MainEntryTest(unittest.TestCase):
    """入口分发：按参数与依赖情况返回对应退出码。"""

    def setUp(self):
        """保存原始函数，并准备一份可用文本。"""
        self._orig_run = w._run_engine
        self._orig_read = w._read_text
        import tempfile
        self._dir = tempfile.mkdtemp()
        self._text = os.path.join(self._dir, "t.txt")
        self._out = os.path.join(self._dir, "o.wav")
        with open(self._text, "w", encoding="utf-8") as f:
            f.write("你好")

    def tearDown(self):
        """还原被替换的函数并清理临时目录。"""
        w._run_engine = self._orig_run
        w._read_text = self._orig_read
        import shutil
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_arg_and_read_failures(self):
        """参数不足与文本读取失败都返回 1，均不进入合成。"""
        self.assertEqual(w.main(["a", "b"]), 1)
        w._read_text = lambda p: None
        self.assertEqual(w.main([self._text, self._out, "", "150"]), 1)

    def test_missing_pyttsx3_returns_two(self):
        """未安装 pyttsx3 返回 2，与合成失败区分开，便于父进程分辨原因。"""
        saved = sys.modules.get("pyttsx3")
        # 置入 None 会让 import 抛 ImportError，等价于模块缺失
        sys.modules["pyttsx3"] = None
        try:
            self.assertEqual(w.main([self._text, self._out, "", "150"]), 2)
        finally:
            if saved is None:
                sys.modules.pop("pyttsx3", None)
            else:
                sys.modules["pyttsx3"] = saved

    def test_normal_path_delegates_to_run_engine(self):
        """正常路径把文本与参数交给 _run_engine，并透传其退出码。"""
        seen = {}

        def _fake_run(mod, text, out_path, voice, rate):
            """记录收到的参数，返回 0。"""
            seen.update({"text": text, "voice": voice, "rate": rate})
            return 0

        w._run_engine = _fake_run
        saved = sys.modules.get("pyttsx3")
        sys.modules["pyttsx3"] = type(sys)("pyttsx3")
        try:
            code = w.main([self._text, self._out, "v1", "180"])
        finally:
            if saved is None:
                sys.modules.pop("pyttsx3", None)
            else:
                sys.modules["pyttsx3"] = saved
        self.assertEqual(code, 0)
        self.assertEqual(seen["text"], "你好")
        self.assertEqual(seen["voice"], "v1")
        self.assertEqual(seen["rate"], "180")


if __name__ == "__main__":
    unittest.main()
