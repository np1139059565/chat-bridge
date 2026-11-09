"""TTS 文字转语音路由 —— 网页版按需合成入口

职责：给网页前端提供两个 HTTP 接口：
- POST /api/voice/tts     把文本合成为 MP3，落到网页音频目录，返回文件名与访问地址；
- GET  /api/voice/voices  列出可用音色，供前端音色选择器使用。

为什么独立成模块：与 web_files_serve 同理，routes/web.py 已贴近行数上限，
新接口单独成蓝图，避免继续膨胀既有文件。

与 web_mirror 的分工：
- web_mirror 面向消息镜像：写死默认音色、带重试与缓存，语义是附加能力不阻塞主流程；
- 本路由面向按需合成：音色可透传、每次独立出片、失败如实上报。
  两者语义不同，故直接调 voice_tts 薄封装，不复用 synthesize_voice。

安全：音频文件名由服务端生成（时间戳 + 随机串），下发沿用既有的
/api/web/audio/<name> 路由，其内部已做目录穿越防护。

依赖：flask、time、secrets、paths、remote_bridge.voice_tts、
remote_bridge.voice_voices、web_bridge.audio_prune
"""

import secrets
import time

from flask import Blueprint, jsonify, request

import app_log
import paths

# 蓝图名不得与既有重复（web / web_files_serve / remote_bridge 等）。
bp = Blueprint("voice", __name__)

# 音频访问地址前缀：与 routes/web_files_serve.py 的下发路由保持一致。
_AUDIO_URL_PREFIX = "/api/web/audio/"


def log(*args):
    """统一前缀打印。"""
    app_log.info("[voice]", *args)


def _import_tts():
    """延迟导入合成模块：remote_bridge 不可用时返回 None（调用方报 500）。

    不在导入期拉起 remote_bridge：与 web_mirror 同理，避免应用启动被
    语音依赖拖垮；语音接口失败只影响本次请求。
    """
    try:
        from remote_bridge import voice_tts
        return voice_tts
    except Exception as e:
        log("合成模块不可用：", e)
        return None


def _new_audio_name():
    """生成音频文件名：毫秒时间戳保证大致有序，随机后缀保证同毫秒不互覆盖。

    web_mirror 只用时间戳（串行调用不会撞）；本接口允许前端连续点按，
    同毫秒两次合成的概率不可忽略，故补随机后缀。
    """
    return "tts_%d_%s.mp3" % (int(time.time() * 1000), secrets.token_hex(4))


def _parse_tts_request(data):
    """抽取并校验合成参数：text 必填非空白字符串，voice 选填。

    voice 仅在是字符串时透传（去首尾空白），其余一律归一为空串走
    引擎默认音色。返回 (text, use_voice, err)，err 非 None 即参数不合法。
    """
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        return None, None, "text_required"
    voice = data.get("voice")
    use_voice = voice.strip() if isinstance(voice, str) else ""
    return text, use_voice, None


def _ensure_audio_dir():
    """确保网页音频目录存在：成功返回 (None, None)，失败返回 (错误码, 原因)。"""
    try:
        paths.WEB_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        return None, None
    except Exception as e:
        log("音频目录不可用：", e)
        return "audio_dir_unavailable", str(e)


def _tts_ready(data):
    """合成前置检查三连：参数 → 合成模块 → 音频目录。

    全部就绪返回 (text, use_voice, tts_mod, None)；任一关失败返回
    (None, None, None, (响应体, 状态码))，调用方原样返回即可，
    避免主流程函数里堆重复的失败分支。
    """
    text, use_voice, err = _parse_tts_request(data)
    if err:
        return None, None, None, (jsonify(success=False, error=err), 400)
    tts_mod = _import_tts()
    if tts_mod is None:
        return None, None, None, (jsonify(success=False, error="tts_unavailable"), 500)
    code, reason = _ensure_audio_dir()
    if code:
        return None, None, None, (jsonify(success=False, error=code, reason=reason), 500)
    return text, use_voice, tts_mod, None


def _run_synthesis(tts_mod, text, use_voice):
    """执行一次合成并计时：底层异常归并为失败，不向上抛。

    返回 (ok, err, 耗时ms, 文件名)；文件名先于调用生成，同毫秒连点
    靠随机后缀互不覆盖（见 _new_audio_name）。
    """
    fname = _new_audio_name()
    out_path = str(paths.WEB_AUDIO_DIR / fname)
    t0 = time.perf_counter()
    try:
        ok, err = tts_mod.text_to_voice(text, out_path, use_voice)
    except Exception as e:
        ok, err = False, str(e)
    ms = (time.perf_counter() - t0) * 1000.0
    return ok, err, ms, fname


def _prune_old_audio():
    """成功合成后回收旧音频：失败只记日志，绝不影响本次响应。"""
    try:
        from web_bridge.audio_prune import prune_audio_files
        prune_audio_files()
    except Exception as e:
        log("回收旧音频失败（不影响本次响应）：", e)


@bp.route("/api/voice/tts", methods=["POST", "OPTIONS"])
def tts():
    """把文本合成为语音：POST {"text": "...", "voice": "..."}。

    编排：_tts_ready 三关检查 → _run_synthesis 计时合成 → 失败上报 500
    带底层原因 / 成功回收旧音频并返回 file、url、voice。
    """
    data = request.get_json(silent=True) or {}
    text, use_voice, tts_mod, fail = _tts_ready(data)
    if fail:
        return fail
    ok, err, ms, fname = _run_synthesis(tts_mod, text, use_voice)
    if not ok:
        log("合成失败 文本=%d 音色=%s 耗时=%.0fms 原因=%s" % (len(text), use_voice, ms, err))
        return jsonify(success=False, error="tts_failed", reason=str(err or "unknown")), 500
    _prune_old_audio()
    log("合成成功 文本=%d 音色=%s 耗时=%.0fms 文件=%s" % (len(text), use_voice, ms, fname))
    return jsonify(success=True, file=fname, url=_AUDIO_URL_PREFIX + fname, voice=use_voice)


@bp.route("/api/voice/voices", methods=["GET", "OPTIONS"])
def voices():
    """列出可用音色：?engine=<名> 可选，透传给音色模块。

    数据源与 /api/bridge/voices（设置页用）相同，路由独立互不影响。
    """
    try:
        from remote_bridge import voice_voices
    except Exception as e:
        log("音色模块不可用：", e)
        return jsonify(success=False, error="voices_unavailable"), 500

    engine = str(request.args.get("engine") or "").strip()
    try:
        items = voice_voices.list_voices(engine)
    except Exception as e:
        log("列音色失败：", e)
        return jsonify(success=False, error="voices_failed", reason=str(e)), 500
    return jsonify(success=True, voices=items or [])
