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
- 每次合成使用「独立线程 + 独立事件循环」，彼此不共享任何循环。
  某次合成卡住只会拖住它自己那条守护线程（随进程回收），
  不会牵连其它合成，从而彻底隔离故障。

依赖：asyncio、os、threading
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
SYNTH_TIMEOUT = 20

# 并发合成上限：同一时刻最多 N 条在线合成，其余排队。
# 既防一次性打爆在线服务，也防线程数无上限增长。
MAX_CONCURRENT_SYNTH = 3
_synth_sem = threading.Semaphore(MAX_CONCURRENT_SYNTH)


def _ensure_import(name):
    """尝试导入可选依赖；失败返回 None。"""
    try:
        return __import__(name)
    except Exception:
        return None


def _synth_thread_body(edge_tts, text, voice, out_path, timeout, result):
    """线程体：新建专属事件循环，跑完一次合成，把结果写回 result。

    @param edge_tts 已导入的 edge_tts 模块
    @param text     待合成文本
    @param voice    音色名
    @param out_path 输出音频路径
    @param timeout  单次合成的协程级超时（秒）
    @param result   结果字典（就地写入 ok / err）
    """
    loop = asyncio.new_event_loop()          # 本线程专属事件循环，独立于其它合成
    asyncio.set_event_loop(loop)             # 绑定到本线程，避免跨线程串用
    try:
        async def _do():
            """单次合成协程：Communicate.save 带协程级超时。"""
            comm = edge_tts.Communicate(text, voice=voice)
            await asyncio.wait_for(comm.save(out_path), timeout=timeout)
        loop.run_until_complete(_do())       # 阻塞本线程直到合成完成或协程超时
        result["ok"] = True                  # 正常产出音频
    except asyncio.TimeoutError:
        result["err"] = "timeout"            # 协程级超时（wait_for 触发）
    except Exception as e:
        result["err"] = str(e)               # 其它合成异常
    finally:
        # 收尾：不显式 loop.close()。
        # edge_tts 遗留的 Proactor 管道对象在本线程循环回收后才被 GC，
        # 其析构函数会调用已不可用的循环，向 stderr 打一条
        # «Exception ignored ... Event loop is closed»。
        # 这是 Python 3.10 + Windows Proactor 的已知无害告警：
        #   - 不影响合成结果（音频已落盘）；
        #   - 不进 app_log，不污染业务日志。
        # 它无法在本层根除，除非放弃「独立循环」这一故障隔离手段；
        # 权衡后保留独立循环，接受该噪音。
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass                             # 收尾异常不影响合成结果


def _synth_in_new_loop(edge_tts, text, voice, out_path, timeout):
    """在独立线程的独立事件循环中执行一次合成。

    设计要点：不与其他合成共享事件循环，因此单条合成卡死不会拖垮全局。
    线程为守护线程：即使协程被超时后仍未真正退出，也不会阻塞调用方，
    进程结束时自动回收；调用方按 join 超时判定失败并返回。

    @param edge_tts 已导入的 edge_tts 模块
    @param text     待合成文本
    @param voice    音色名
    @param out_path 输出音频路径
    @param timeout  单次合成的协程级超时（秒）
    @returns (ok, error)；成功时 error 为空串
    """
    result = {"ok": False, "err": ""}
    t = threading.Thread(target=_synth_thread_body,
                         args=(edge_tts, text, voice, out_path, timeout, result),
                         daemon=True, name="tts-synth")
    t.start()                                    # 启动独立合成线程
    t.join(timeout=timeout + 10)                 # 外层等待略长于协程超时，确保协程超时先触发
    if t.is_alive():
        # 线程仍未结束：协程未被真正取消而卡住。该线程为守护线程，直接放弃，
        # 不影响其它合成，也不再占住共享循环。
        return False, "edge-tts 合成超时（%d 秒）" % timeout
    if result["ok"]:
        return True, ""
    if result["err"] == "timeout":
        return False, "edge-tts 合成超时（%d 秒）" % timeout
    return False, "edge-tts 合成失败：%s" % result["err"]


def text_to_voice(text, out_path, voice=None):
    """把文本合成为语音文件。

    @param text     待合成文本（已去掉 [VOICE] 标记）
    @param out_path 输出文件路径（.mp3）
    @param voice    edge-tts 音色名；缺省用默认中文音色
    @returns (ok, error)；成功时 error 为空串
    """
    text = (text or "").strip()                     # 规整文本，去首尾空白
    if not text:
        return False, "待合成文本为空"              # 空文本无需合成
    edge_tts = _ensure_import("edge_tts")           # 惰性导入可选依赖
    if edge_tts is None:
        return False, "未安装 edge-tts，无法合成语音"
    voice = voice or DEFAULT_VOICE                  # 未指定则用默认音色
    # 并发闸门：最多 MAX_CONCURRENT_SYNTH 条同时在线合成，其余排队等待。
    with _synth_sem:
        ok, err = _synth_in_new_loop(edge_tts, text, voice, out_path, SYNTH_TIMEOUT)
    if not ok:
        return False, err                           # 合成失败，直接返回原因
    # 合成结果为空文件也算失败，避免发一个空语音
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        return False, "edge-tts 未产出有效音频"
    return True, ""
