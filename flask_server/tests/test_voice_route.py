"""网页版语音路由测试 —— /api/voice/tts 与 /api/voice/voices

为什么需要：任务书新增网页按需合成接口，需要验证参数校验、成功路径、
失败路径与音色列出行为，避免「前端一调才发现 500」。

本文件覆盖：
- POST /api/voice/tts：缺参 / 类型错 / 空白文本 → 400；成功 → 200，
  文件落在重定向后的音频目录、url 指向下发路由；voice 透传；
  同文本两次合成文件名不同；引擎失败 → 500 且不留残留文件；
  成功后触发旧音频回收、回收失败不影响响应；
- GET /api/voice/voices：engine 透传；底层异常 → 500。

隔离策略：
- conftest.py 的 autouse 夹具已把 paths.WEB_AUDIO_DIR 重定向到用例独立
  临时目录，音频文件不会写进真实目录；
- 合成模块用 routes.voice._import_tts 替身（FakeTts），不依赖本机 TTS 引擎；
- 音色模块向 sys.modules 注入假 remote_bridge.voice_voices；
- 旧音频回收用 monkeypatch 拦截，不触碰真实回收逻辑。

运行命令：
    python -m pytest flask_server/tests/test_voice_route.py -v
"""

import sys
import types

from flask import Flask

import paths
from routes.voice import bp as voice_bp


def make_client():
    """只注册被测蓝图的最小应用：与 test_web_route 同款做法。"""
    app = Flask(__name__)
    app.register_blueprint(voice_bp)
    return app.test_client()


class FakeTts:
    """合成替身：可配置成功/失败，并记录收到的调用参数。"""

    def __init__(self, ok=True, err=None):
        self.ok = ok
        self.err = err
        self.calls = []

    def text_to_voice(self, text, out_path, voice):
        self.calls.append({"text": text, "out_path": out_path, "voice": voice})
        if self.ok:
            with open(out_path, "wb") as f:
                f.write(b"fake-mp3")
            return True, ""
        return False, self.err


def install_fake_tts(monkeypatch, fake):
    """把 routes.voice._import_tts 替换为恒返替身的函数。"""
    monkeypatch.setattr("routes.voice._import_tts", lambda: fake)


def install_fake_voices(monkeypatch, items=None, err=None):
    """向 sys.modules 注入假 remote_bridge.voice_voices，返回该假模块。"""
    mod = types.ModuleType("remote_bridge.voice_voices")

    def list_voices(engine=""):
        if err is not None:
            raise RuntimeError(err)
        return items if items is not None else []

    mod.list_voices = list_voices
    pkg = types.ModuleType("remote_bridge")
    monkeypatch.setitem(sys.modules, "remote_bridge", pkg)
    monkeypatch.setitem(sys.modules, "remote_bridge.voice_voices", mod)
    return mod


class TestTtsValidation:
    """POST /api/voice/tts 参数校验：不对就 400，且不触碰合成模块。"""

    def test_missing_text_400(self, monkeypatch):
        """缺 text 字段 → 400，合成模块未被调用。"""
        fake = FakeTts()
        install_fake_tts(monkeypatch, fake)
        resp = make_client().post("/api/voice/tts", json={})
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "text_required"
        assert fake.calls == []

    def test_non_string_text_400(self, monkeypatch):
        """text 是数字等非字符串 → 400。"""
        fake = FakeTts()
        install_fake_tts(monkeypatch, fake)
        resp = make_client().post("/api/voice/tts", json={"text": 123})
        assert resp.status_code == 400
        assert fake.calls == []

    def test_blank_text_400(self, monkeypatch):
        """text 全空白 → 400。"""
        fake = FakeTts()
        install_fake_tts(monkeypatch, fake)
        resp = make_client().post("/api/voice/tts", json={"text": "   \n "})
        assert resp.status_code == 400
        assert fake.calls == []


class TestTtsSuccess:
    """POST /api/voice/tts 成功路径：落盘、命名、url、音色、回收。"""

    def test_ok_writes_file_and_url(self, monkeypatch):
        """成功 → 200：文件落重定向目录，url 指向下发路由，回收被触发。"""
        fake = FakeTts()
        install_fake_tts(monkeypatch, fake)
        pruned = []
        monkeypatch.setattr(
            "web_bridge.audio_prune.prune_audio_files",
            lambda: pruned.append(1))
        resp = make_client().post("/api/voice/tts", json={"text": "你好"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["file"].startswith("tts_") and body["file"].endswith(".mp3")
        assert body["url"] == "/api/web/audio/" + body["file"]
        assert (paths.WEB_AUDIO_DIR / body["file"]).is_file()
        assert pruned == [1]

    def test_voice_passed_through(self, monkeypatch):
        """voice 非空 → 原样透传给合成模块并回显。"""
        fake = FakeTts()
        install_fake_tts(monkeypatch, fake)
        resp = make_client().post(
            "/api/voice/tts", json={"text": "你好", "voice": "Huihui"})
        assert resp.status_code == 200
        assert resp.get_json()["voice"] == "Huihui"
        assert fake.calls[0]["voice"] == "Huihui"

    def test_empty_voice_uses_default(self, monkeypatch):
        """voice 空白 → 归一为空串（引擎默认音色）。"""
        fake = FakeTts()
        install_fake_tts(monkeypatch, fake)
        resp = make_client().post(
            "/api/voice/tts", json={"text": "你好", "voice": "  "})
        assert resp.status_code == 200
        assert resp.get_json()["voice"] == ""
        assert fake.calls[0]["voice"] == ""

    def test_same_text_twice_distinct_names(self, monkeypatch):
        """同文本连点两次 → 两个不同文件名，互不覆盖。"""
        fake = FakeTts()
        install_fake_tts(monkeypatch, fake)
        client = make_client()
        f1 = client.post("/api/voice/tts", json={"text": "重复"}).get_json()["file"]
        f2 = client.post("/api/voice/tts", json={"text": "重复"}).get_json()["file"]
        assert f1 != f2


class TestTtsFailure:
    """POST /api/voice/tts 失败路径：500 带原因，不留残留。"""

    def test_engine_failure_500_no_file(self, monkeypatch):
        """引擎失败 → 500，原因带底层信息，目录里无残留文件。"""
        fake = FakeTts(ok=False, err="引擎超时")
        install_fake_tts(monkeypatch, fake)
        resp = make_client().post("/api/voice/tts", json={"text": "你好"})
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["error"] == "tts_failed"
        assert "引擎超时" in body["reason"]
        assert list(paths.WEB_AUDIO_DIR.glob("tts_*")) == []

    def test_tts_unavailable_500(self, monkeypatch):
        """合成模块不可用 → 500，error=tts_unavailable。"""
        monkeypatch.setattr("routes.voice._import_tts", lambda: None)
        resp = make_client().post("/api/voice/tts", json={"text": "你好"})
        assert resp.status_code == 500
        assert resp.get_json()["error"] == "tts_unavailable"

    def test_prune_failure_not_break_response(self, monkeypatch):
        """回收环节炸了 → 响应仍 200（回收失败不影响本次结果）。"""
        fake = FakeTts()
        install_fake_tts(monkeypatch, fake)

        def boom():
            raise RuntimeError("回收炸了")

        monkeypatch.setattr(
            "web_bridge.audio_prune.prune_audio_files", boom)
        resp = make_client().post("/api/voice/tts", json={"text": "你好"})
        assert resp.status_code == 200
        assert (paths.WEB_AUDIO_DIR / resp.get_json()["file"]).is_file()


class TestVoices:
    """GET /api/voice/voices：engine 透传与异常分支。"""

    def test_engine_passed_through(self, monkeypatch):
        """?engine=sapi → 原样传给 list_voices，数据原样返回。"""
        mod = install_fake_voices(
            monkeypatch, items=[{"name": "Huihui", "id": "x"}])
        seen = []
        orig = mod.list_voices

        def spy(engine=""):
            seen.append(engine)
            return orig(engine)

        mod.list_voices = spy
        resp = make_client().get("/api/voice/voices?engine=sapi")
        assert resp.status_code == 200
        assert resp.get_json()["voices"] == [{"name": "Huihui", "id": "x"}]
        assert seen == ["sapi"]

    def test_failure_500(self, monkeypatch):
        """音色模块异常 → 500，error=voices_failed 且带原因。"""
        install_fake_voices(monkeypatch, err="引擎不可用")
        resp = make_client().get("/api/voice/voices")
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["error"] == "voices_failed"
        assert "引擎不可用" in body["reason"]
