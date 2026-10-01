"""远程桥接 —— 语音识别（SILK 解码 + vosk 转文字）

职责：把 QQ 发来的语音文件（SILK 格式）转成文字。

链路：
  SILK 文件 → pilk 解码 → int16 裸 PCM
           → wave 标准库加 WAV 头 → WAV 文件
           → vosk 识别 → 文字

依赖策略：
- pilk、vosk 均为可选依赖，未安装时本模块对应函数返回错误说明，
  不影响桥接其余功能（与 qq_client 对 websocket-client 的处理一致）。
- 不依赖 ffmpeg、不依赖 numpy：pilk 出的是 int16 裸 PCM，
  用标准库 wave 就能加头，省去外部二进制依赖。

采样率对齐：
- pilk 的 pcm_rate 默认 24000，与 QQ 语音原生采样率一致；
- vosk 标准中文模型期望 16000Hz 单声道 16bit，
  故识别前若采样率不符，做一次线性重采样（纯 Python，无需 numpy）。
"""
import os
import struct
import wave

from . import bridge_store, bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][voice]", *args)


# vosk 模型目录：优先环境变量 VOSK_MODEL_PATH，未设时回退到
# 工程根下的约定目录 models/vosk-model-cn-0.22，做到开箱即用。
def _default_model_path():
    """解析默认 vosk 模型目录：环境变量优先，否则用工程根下的约定路径。"""
    env = os.environ.get("VOSK_MODEL_PATH", "")
    if env and os.path.isdir(env):
        return env
    import paths
    guess = paths.PROJECT_ROOT / "models" / "vosk-model-cn-0.22"
    return str(guess)


# vosk 识别期望的采样率
VOSK_RATE = 16000


def _ensure_import(name):
    """尝试导入一个可选依赖；成功返回模块，失败返回 None。"""
    try:
        return __import__(name)
    except Exception:
        return None


def silk_to_wav(silk_path, wav_path, pcm_rate=24000):
    """把 SILK 文件解码为 WAV 文件。

    @param silk_path SILK 源文件路径
    @param wav_path  输出 WAV 路径
    @param pcm_rate  pilk 解码采样率，默认 24000（QQ 语音原生）
    @returns (ok, error)；成功时 error 为空串
    """
    pilk = _ensure_import("pilk")
    if pilk is None:
        return False, "未安装 pilk，无法解码 SILK"
    # pilk 的 C 层输出的是 int16 裸 PCM（无头），先落到一个临时 pcm 文件
    tmp_pcm = wav_path + ".pcm"
    try:
        dec = pilk.SilkDecoder(pcm_rate=pcm_rate)
        # decode 内部会自动识别 \x02#!SILK_V3 与 !SILK_V3 两种头，无需手动剥字节
        dec.decode(silk_path, tmp_pcm)
    except Exception as e:
        return False, "pilk 解码失败：%s" % e
    # 把裸 PCM 加 WAV 头，供后续识别使用
    try:
        with open(tmp_pcm, "rb") as f:
            pcm = f.read()
        _write_wav(wav_path, pcm, pcm_rate)
    except Exception as e:
        return False, "封装 WAV 失败：%s" % e
    finally:
        # 临时 PCM 用完即删，避免留垃圾
        try:
            os.remove(tmp_pcm)
        except OSError:
            pass
    return True, ""


def _write_wav(wav_path, pcm_bytes, rate):
    """把 int16 裸 PCM 字节写入 WAV 文件（单声道、16bit）。"""
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)          # 单声道
        w.setsampwidth(2)          # 16bit = 2 字节
        w.setframerate(rate)       # 采样率
        w.writeframes(pcm_bytes)   # 写入 PCM 数据


def _resample_int16(pcm_bytes, src_rate, dst_rate):
    """对 int16 PCM 做线性重采样（纯 Python，避免引入 numpy）。

    @param pcm_bytes 原始 int16 小端字节
    @param src_rate  原采样率
    @param dst_rate  目标采样率
    @returns 重采样后的 int16 字节
    """
    if src_rate == dst_rate or not pcm_bytes:
        return pcm_bytes
    n = len(pcm_bytes) // 2                 # 样本数
    samples = struct.unpack("<%dh" % n, pcm_bytes[:n * 2])
    ratio = dst_rate / float(src_rate)
    out_n = int(n * ratio)
    out = []
    for i in range(out_n):
        pos = i / ratio                     # 目标第 i 点对应的源位置
        i0 = int(pos)
        i1 = min(i0 + 1, n - 1)
        frac = pos - i0
        # 相邻两点线性插值
        out.append(int(samples[i0] * (1 - frac) + samples[i1] * frac))
    return struct.pack("<%dh" % out_n, *out)


def wav_to_text(wav_path, model_path=None):
    """用 vosk 识别 WAV 文件，返回文字。

    @param wav_path   WAV 文件路径
    @param model_path vosk 模型目录；缺省用环境变量 VOSK_MODEL_PATH
    @returns (text, error)；成功时 error 为空串
    """
    vosk = _ensure_import("vosk")
    if vosk is None:
        return "", "未安装 vosk，无法识别语音"
    model_path = model_path or _default_model_path()
    if not model_path or not os.path.isdir(model_path):
        return "", "未找到 vosk 模型目录（设环境变量 VOSK_MODEL_PATH，或放到 models/vosk-model-cn-0.22）"
    try:
        model = vosk.Model(model_path)
        with wave.open(wav_path, "rb") as w:
            rate = w.getframerate()
            raw = w.readframes(w.getnframes())
        # vosk 期望 16kHz 单声道 16bit；采样率不符则重采样
        if rate != VOSK_RATE:
            raw = _resample_int16(raw, rate, VOSK_RATE)
            rate = VOSK_RATE
        rec = vosk.KaldiRecognizer(model, rate)
        rec.AcceptWaveform(raw)
        import json
        result = json.loads(rec.FinalResult())
        return (result.get("text") or "").strip(), ""
    except Exception as e:
        return "", "vosk 识别失败：%s" % e


def voice_file_to_text(silk_path):
    """对外主入口：QQ 语音文件 → 文字。

    先解码 SILK 为 WAV，再走 vosk 识别；任一步失败返回错误说明。
    产出的 WAV 落语音临时目录，识别后即删。
    @param silk_path SILK 文件路径
    @returns (text, error)
    """
    import paths
    os.makedirs(paths.VOICE_DIR, exist_ok=True)
    wav_path = str(paths.VOICE_DIR / (os.path.basename(silk_path) + ".wav"))
    ok, err = silk_to_wav(silk_path, wav_path)
    if not ok:
        return "", err
    try:
        return wav_to_text(wav_path)
    finally:
        # WAV 中间产物用完即删
        try:
            os.remove(wav_path)
        except OSError:
            pass
