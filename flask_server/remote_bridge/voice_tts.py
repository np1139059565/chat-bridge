"""远程桥接 —— 语音合成（edge-tts 文字转语音）

职责：把 AI 回复中「适合朗读」的文本合成为语音文件，供发回 QQ。

链路：
  文本 → edge-tts 合成 → MP3 文件

依赖策略：
- edge-tts 为可选依赖，未安装时返回错误说明，不影响桥接其余功能。
- edge-tts 是在线服务（微软），免 key、免费；断网时合成失败，
  此时返回错误，由调用方决定是否降级（不发语音）。

并发模型（关键）：
- edge-tts 的 Communicate.save 是协程，必须跑在事件循环里。
- 此前每次合成用 asyncio.run() 新建/销毁事件循环：多线程同时调用时，
  事件循环的创建与销毁会互相干扰（Windows Proactor 上残留管道对象，
  反复报 RuntimeError: Event loop is closed），并可能让合成线程卡住。
- 改为：单个专职线程长期持有一个事件循环，所有合成请求投递到它上面执行。
  循环只创建一次、永不销毁，从根本上消除反复创建销毁的冲突。

依赖：asyncio、concurrent.futures、os、threading
"""
import asyncio
import concurrent.futures
import os
import threading

from . import bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][tts]", *args)


# 默认中文音色：晓晓（女声，通用场景自然）
DEFAULT_VOICE = os.environ.get("EDGE_TTS_VOICE", "zh-CN-XiaoxiaoNeural")

# 单次合成的超时（秒）：edge-tts 是在线服务，网络差时会长时间挂住。
# 不加超时，每个挂住的合成会一直占着合成循环，让后续合成全部排队等待。
SYNTH_TIMEOUT = 20

# 并发合成上限：同一时刻最多 N 条在线合成，其余排队。
# 既防一次性打爆在线服务，也防网络请求数无上限增长。
MAX_CONCURRENT_SYNTH = 3
_synth_sem = threading.Semaphore(MAX_CONCURRENT_SYNTH)


# ---------- 专职事件循环线程 ----------
# 事件循环只创建一次，长期复用；合成请求经 run_coroutine_threadsafe 投递。
_loop = None
_loop_ready = threading.Event()
_loop_lock = threading.Lock()


def _loop_thread_main():
    """专职线程入口：建一个事件循环并长期运行（永不主动销毁）。"""
    global _loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    with _loop_lock:
        _loop = loop
    _loop_ready.set()
    loop.run_forever()


def _ensure_loop():
    """确保专职事件循环线程已启动，返回事件循环对象。

    幂等：重复调用只启动一个循环线程。首次调用会等待循环就绪。
    """
    if not _loop_ready.is_set():
        with _loop_lock:
            if _loop is None:
                threading.Thread(
                    target=_loop_thread_main, daemon=True, name="tts-loop"
                ).start()
    _loop_ready.wait(timeout=5)
    return _loop


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
    loop = _ensure_loop()
    if loop is None:
        return False, "语音合成事件循环不可用"
    # 并发闸门：最多 MAX_CONCURRENT_SYNTH 条同时在线合成，其余排队等待。
    with _synth_sem:
        try:
            # 把合成协程投递到长期复用的循环上执行；此处阻塞等待结果。
            # wait_for 强制超时：网络差时不让合成无限挂住。
            async def _do():
                comm = edge_tts.Communicate(text, voice=voice)
                await asyncio.wait_for(comm.save(out_path), timeout=SYNTH_TIMEOUT)
            fut = asyncio.run_coroutine_threadsafe(_do(), loop)
            # 结果等待略长于协程超时，确保协程自身超时先触发
            fut.result(timeout=SYNTH_TIMEOUT + 10)
        except concurrent.futures.TimeoutError:
            return False, "edge-tts 合成超时（%d 秒）" % SYNTH_TIMEOUT
        except asyncio.TimeoutError:
            return False, "edge-tts 合成超时（%d 秒）" % SYNTH_TIMEOUT
        except Exception as e:
            return False, "edge-tts 合成失败：%s" % e
    # 合成结果为空文件也算失败，避免发一个空语音
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        return False, "edge-tts 未产出有效音频"
    return True, ""
