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
import threading

from . import bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][tts]", *args)


# 默认中文音色：晓晓（女声，通用场景自然）
DEFAULT_VOICE = os.environ.get("EDGE_TTS_VOICE", "zh-CN-XiaoxiaoNeural")

# 单次合成的超时（秒）：edge-tts 是在线服务，网络差时会长时间挂住。
# 不加超时，每个挂住的合成都占一条线程不放，堆积起来会把服务拖垮，
# 尤其在网络抖动、多条语音同时排队时。
SYNTH_TIMEOUT = 20

# 并发合成上限：同时最多 N 条在线合成，其余排队。
# 既防一次性打爆在线服务，也防线程数无上限增长。
MAX_CONCURRENT_SYNTH = 3
_synth_sem = threading.Semaphore(MAX_CONCURRENT_SYNTH)


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
    # 并发闸门：最多 MAX_CONCURRENT_SYNTH 条同时在线合成，其余排队等待。
    # 拿不到闸门就等——排队胜过无限开线程打爆服务。
    with _synth_sem:
        try:
            # Communicate.save 是协程：用 asyncio.run 包成同步调用。
            # 用 wait_for 强制超时：网络差时不让合成无限挂住线程。
            async def _do():
                comm = edge_tts.Communicate(text, voice=voice)
                await asyncio.wait_for(comm.save(out_path), timeout=SYNTH_TIMEOUT)
            asyncio.run(_do())
        except asyncio.TimeoutError:
            return False, "edge-tts 合成超时（%d 秒）" % SYNTH_TIMEOUT
        except Exception as e:
            return False, "edge-tts 合成失败：%s" % e
    # 合成结果为空文件也算失败，避免发一个空语音
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        return False, "edge-tts 未产出有效音频"
    return True, ""
