"""远程桥接 —— 语音合成（edge-tts 文字转语音）

职责：把 AI 回复中「适合朗读」的文本合成为语音文件，供发回 QQ。

链路：
  文本 → edge-tts 合成 → MP3 文件

依赖策略：
- edge-tts 为可选依赖，未安装时返回错误说明，不影响桥接其余功能。
- edge-tts 是在线服务（微软），免 key、免费；断网时合成失败，
  此时返回错误，由调用方决定是否降级（不发语音）。

实现要点：
- edge-tts 的 Communicate.save 是协程，这里用 asyncio.run 包成同步调用，
  因为调用方（message_router）在同步线程里。
"""
import asyncio
import os

from . import bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][tts]", *args)


# 默认中文音色：晓晓（女声，通用场景自然）
DEFAULT_VOICE = os.environ.get("EDGE_TTS_VOICE", "zh-CN-XiaoxiaoNeural")


def _ensure_import(name):
    """尝试导入可选依赖；失败返回 None。"""
    try:
        return __import__(name)
    except Exception:
        return None


def text_to_voice(text, out_path, voice=None):
    """把文本合成为语音文件。

    @param text     待合成文本（已去掉 [VOICE] 标记）
    @param out_path 输出文件路径（.mp3）
    @param voice    edge-tts 音色名；缺省用默认中文音色
    @returns (ok, error)；成功时 error 为空串
    """
    text = (text or "").strip()
    if not text:
        return False, "待合成文本为空"
    edge_tts = _ensure_import("edge_tts")
    if edge_tts is None:
        return False, "未安装 edge-tts，无法合成语音"
    voice = voice or DEFAULT_VOICE
    try:
        # Communicate.save 是协程：用 asyncio.run 包成同步调用
        async def _do():
            comm = edge_tts.Communicate(text, voice=voice)
            await comm.save(out_path)
        asyncio.run(_do())
    except Exception as e:
        return False, "edge-tts 合成失败：%s" % e
    # 合成结果为空文件也算失败，避免发一个空语音
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        return False, "edge-tts 未产出有效音频"
    return True, ""
