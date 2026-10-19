"""远程桥接 —— 语音合成（多引擎，统一输出 MP3）

职责：把 AI 回复中「适合朗读」的文本合成为 MP3 文件，供发回 QQ 或网页播放。

引擎：
  piper    本地神经网络合成，输出 WAV，再编码为 MP3；离线、延迟低。
  pyttsx3  调用系统 SAPI5 语音，输出 WAV，再编码为 MP3；离线、零安装。
  edge_tts 微软在线合成，直接输出 MP3；需联网，非官方接口。

安装分工（重要）：
  pyttsx3 是纯 Python 包，pip install -r requirements.txt 即可装好。
  piper 是「独立可执行文件 + ONNX 模型」，二者都不是 Python 包，pip 装不了，
  需在仓库根目录跑一次 python scripts/setup_piper.py 获取。
  未装 piper 时 auto 模式自动回落到 pyttsx3，不影响服务启动。

切换方式：配置 bridge.push.voice_engine。
  - 固定引擎名（piper / pyttsx3 / edge_tts）：失败即返回错误，不降级。
  - auto：按 bridge.push.voice_fallback 的逗号分隔顺序逐个尝试。

对外契约（保持不变）：
  text_to_voice(text, out_path) -> (ok, error)
  无论内部用哪个引擎，最终都产出 out_path 指定的 MP3 文件。
  这样两个调用方（message_voice / web_mirror）无需感知引擎差异。

并发模型（关键）：
- edge-tts 的 Communicate.save 是协程，必须跑在事件循环里。
- 每次合成使用「独立线程 + 独立事件循环」，彼此不共享任何循环。
  某次合成卡住只会拖住它自己那条守护线程（随进程回收），
  不会牵连其它合成，从而彻底隔离故障。
- 本地引擎（piper / pyttsx3）是同步阻塞调用，同样受并发信号量约束，
  防止同时拉起过多子进程或 COM 实例。

依赖：asyncio、os、subprocess、shutil、threading、wave
"""
import asyncio
import os
import shutil
import subprocess
import threading

from . import bridge_log
from . import voice_mp3


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][tts]", *args)


# 默认中文音色：晓晓（女声，通用场景自然）。edge_tts 引擎使用；
# web_mirror 会通过 getattr 取这个名字，故必须保留该模块级变量。
DEFAULT_VOICE = os.environ.get("EDGE_TTS_VOICE", "zh-CN-XiaoxiaoNeural")

# 单次合成的超时（秒）：在线服务网络差、或本地模型首次加载时会挂住。
SYNTH_TIMEOUT = 20

# 并发合成上限取自全项目统一来源（app_limits）：同一时刻最多 N 条合成，
# 其余排队。既防一次性打爆在线服务，也防线程/子进程数无上限增长。
from app_limits import MAX_CONCURRENT_SYNTH
_synth_sem = threading.Semaphore(MAX_CONCURRENT_SYNTH)


# ==================== 一、配置读取 ====================

def _load_voice_cfg():
    """读取语音合成相关配置，返回扁平化的字典。

    配置来源为 bridge.push 分区（见 bridge_store），读取失败时返回空字典，
    由各调用点用内置默认值兜底，保证配置缺失也不影响合成。
    @returns 配置字典（可能为空）
    """
    try:
        from . import bridge_store
        push = bridge_store.get_config().get("push") or {}
        return push
    except Exception as e:
        log("读取语音配置失败，按默认处理：", e)
        return {}


def _safe_remove(path):
    """删除文件，忽略不存在或占用等异常。

    @param path 待删除的文件路径
    """
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass



# ==================== 三、edge-tts 引擎（在线） ====================

def _synth_thread_body(edge_tts, text, voice, out_path, timeout, result):
    """线程体：新建专属事件循环，跑完一次在线合成，把结果写回 result。

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
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass                             # 收尾异常不影响合成结果


def _synth_in_new_loop(edge_tts, text, voice, out_path, timeout):
    """在独立线程的独立事件循环中执行一次在线合成。

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
        # 线程仍未结束：协程未被真正取消而卡住。该线程为守护线程，直接放弃。
        return False, "edge-tts 合成超时（%d 秒）" % timeout
    if result["ok"]:
        return True, ""
    if result["err"] == "timeout":
        return False, "edge-tts 合成超时（%d 秒）" % timeout
    return False, "edge-tts 合成失败：%s" % result["err"]


def _synth_edge(text, out_path, voice):
    """在线引擎：把文本合成为 MP3，直接写到 out_path。

    @param text     待合成文本
    @param out_path 输出 MP3 路径
    @param voice    音色名；为空时用默认中文音色
    @returns (ok, error)
    """
    try:
        edge_tts = __import__("edge_tts")           # 惰性导入可选依赖
    except Exception:
        return False, "未安装 edge-tts"
    voice = voice or DEFAULT_VOICE                  # 未指定则用默认音色
    ok, err = _synth_in_new_loop(edge_tts, text, voice, out_path, SYNTH_TIMEOUT)
    if not ok:
        return False, err                           # 合成失败，直接返回原因
    # 合成结果为空文件也算失败，避免发一个空语音
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        return False, "edge-tts 未产出有效音频"
    return True, ""


# ==================== 四、Piper 引擎（本地） ====================

def _resolve_piper(cfg):
    """确定 Piper 的可执行文件与模型路径。

    配置显式指定优先；留空时回落到工程内 models/tts/piper 目录，
    再回落到 PATH 里的 piper 命令。
    @param cfg 语音配置字典
    @returns (exe, model)；未找到时对应项为空串
    """
    import paths
    exe = (cfg.get("piper_exe") or "").strip()
    if not exe:
        # 工程内默认位置：models/tts/piper/piper.exe
        cand = paths.PIPER_DIR / "piper.exe"
        if cand.exists():
            exe = str(cand)
        else:
            # 再找 PATH；Windows 下 where 会带 .exe，shutil 自动处理
            exe = shutil.which("piper") or ""
    model = (cfg.get("piper_model") or "").strip()
    if not model:
        # 工程内默认模型名；与 .onnx.json 需同目录同前缀
        cand = paths.PIPER_DIR / "zh_CN-huayan-medium.onnx"
        if cand.exists():
            model = str(cand)
    return exe, model


def _synth_piper(text, out_path, cfg):
    """本地引擎：调 piper 合成 WAV，再编码为 MP3。

    通过子进程调用 CLI，与原有「独立进程 + 超时」的故障隔离模型一致。
    文本经 stdin 传入，避免命令行长度限制与编码问题。
    @param text     待合成文本
    @param out_path 输出 MP3 路径
    @param cfg      语音配置字典
    @returns (ok, error)
    """
    exe, model = _resolve_piper(cfg)
    if not exe:
        return False, "未找到 piper 可执行文件"
    if not model:
        return False, "未找到 Piper 模型"
    if not os.path.exists(model):
        return False, "Piper 模型不存在：%s" % model
    # Piper 需要同名的 .onnx.json 配置；缺了会启动即报错，先显式检查
    if not os.path.exists(model + ".json"):
        return False, "Piper 模型配置缺失：%s.json" % model

    wav_path = out_path + ".tmp.wav"               # 临时 WAV，转换后删除
    try:
        # 用 stdin 喂文本；输出文件由 --output_file 指定
        proc = subprocess.run(
            [exe, "--model", model, "--output_file", wav_path],
            input=text.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=SYNTH_TIMEOUT,
        )
        if proc.returncode != 0:
            # 只截取前 200 字符，避免日志被大段报错淹没
            detail = proc.stderr.decode("utf-8", "replace")[:200]
            return False, "piper 退出码 %d：%s" % (proc.returncode, detail)
        if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
            return False, "piper 未产出有效音频"
        return voice_mp3.ensure_mp3(wav_path, out_path)     # 统一转 MP3
    except subprocess.TimeoutExpired:
        return False, "piper 合成超时（%d 秒）" % SYNTH_TIMEOUT
    except Exception as e:
        return False, "piper 合成异常：%s" % e
    finally:
        _safe_remove(wav_path)                     # 无论成败都清临时文件


# ==================== 五、pyttsx3 引擎（系统语音） ====================

def _synth_pyttsx3(text, out_path, cfg):
    """系统引擎：调 Windows SAPI5 合成 WAV，再编码为 MP3。

    为何在独立子进程里跑（关键）：
        SAPI 是进程级单例资源。若在主进程里把 runAndWait 放进守护线程、
        超时后放弃等待，那个线程不会结束——它继续卡在 SAPI 调用里，
        永久占住这份资源。每失败一次就多一个僵尸线程，最终所有合成都在
        闸门处排队超时，只能重启恢复。
        改为子进程后，超时直接杀掉整个进程，SAPI 随进程被系统回收，
        主进程不残留任何状态，失败只影响这一次调用。

    @param text     待合成文本
    @param out_path 输出 MP3 路径
    @param cfg      语音配置字典
    @returns (ok, error)
    """
    import subprocess
    import sys
    import tempfile

    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pyttsx3_worker.py")
    if not os.path.exists(worker):
        return False, "未找到 pyttsx3 合成脚本"

    wav_path = out_path + ".tmp.wav"
    text_path = out_path + ".tmp.txt"
    voice = (cfg.get("pyttsx3_voice") or "").strip()
    try:
        rate = int(cfg.get("pyttsx3_rate") or 150)
    except Exception:
        rate = 150

    # 文本走临时文件而非命令行：朗读文本可能很长、含引号换行，命令行转义易出错
    try:
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(text or "")
    except OSError as e:
        return False, "写入合成文本失败：%s" % e

    try:
        proc = subprocess.Popen(
            [sys.executable, worker, text_path, wav_path, voice, str(rate)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            _, err = proc.communicate(timeout=SYNTH_TIMEOUT)
        except subprocess.TimeoutExpired:
            # 超时：连同子进程一并杀掉，SAPI 随进程回收，主进程不留僵尸
            proc.kill()
            try:
                proc.communicate(timeout=5)
            except Exception:
                pass
            return False, "pyttsx3 合成超时（%d 秒）" % SYNTH_TIMEOUT
        if proc.returncode != 0:
            detail = (err or b"").decode("utf-8", "replace").strip()[:120]
            return False, "pyttsx3 失败：%s" % (detail or ("退出码 %d" % proc.returncode))
        if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
            return False, "pyttsx3 未产出有效音频"
        return voice_mp3.ensure_mp3(wav_path, out_path)     # 统一转 MP3
    except Exception as e:
        return False, "pyttsx3 异常：%s" % e
    finally:
        _safe_remove(text_path)                # 清临时文本
        _safe_remove(wav_path)                 # 清临时 WAV



# ==================== 六、分发与入口 ====================

def _dispatch(engine, text, out_path, voice, cfg):
    """按引擎名调用对应实现，统一产出 MP3。

    @param engine   引擎名
    @param text     待合成文本
    @param out_path 输出 MP3 路径
    @param voice    edge 音色名（其它引擎忽略）
    @param cfg      语音配置字典
    @returns (ok, error)
    """
    if engine == "edge_tts":
        # 音色来源：调用方显式指定 > 配置项 > 内置默认。
        # 与 piper / pyttsx3 一致，三类引擎都能从配置切音色。
        v = voice or (cfg.get("edge_tts_voice") or "")
        return _synth_edge(text, out_path, v)
    if engine == "piper":
        return _synth_piper(text, out_path, cfg)
    if engine == "pyttsx3":
        return _synth_pyttsx3(text, out_path, cfg)
    return False, "未知语音引擎：%s" % engine


def _engine_order(cfg):
    """解析配置，得出本次要依次尝试的引擎列表。

    固定引擎返回单元素列表（失败不降级）；auto 按 fallback 顺序展开。
    @param cfg 语音配置字典
    @returns 引擎名列表（可能为空）
    """
    engine = (cfg.get("voice_engine") or "auto").strip().lower()
    if engine != "auto":
        return [engine]                            # 固定引擎：只试这一个
    raw = (cfg.get("voice_fallback") or "piper,pyttsx3,edge_tts")
    order = [e.strip().lower() for e in str(raw).split(",") if e.strip()]
    return order or ["edge_tts"]                   # 兜底：至少保留在线引擎


def text_to_voice(text, out_path, voice=None):
    """把文本合成为语音文件（对外唯一入口）。

    @param text     待合成文本（已去掉 [VOICE] 标记）
    @param out_path 输出文件路径（.mp3）
    @param voice    edge 引擎音色名；缺省用默认中文音色
    @returns (ok, error)；成功时 error 为空串
    """
    text = (text or "").strip()                     # 规整文本，去首尾空白
    if not text:
        return False, "待合成文本为空"              # 空文本无需合成

    cfg = _load_voice_cfg()                         # 读配置（失败为空字典）
    order = _engine_order(cfg)                      # 得出尝试顺序
    if not order:
        return False, "未配置可用的语音引擎"

    # 并发闸门：最多 MAX_CONCURRENT_SYNTH 条同时合成，其余排队等待。
    #
    # 关键：必须带超时获取，不能用 `with _synth_sem`。
    # 本地引擎（pyttsx3 → SAPI）的 runAndWait 可能永久不返回，一旦卡住就会
    # 永久占住一个信号量名额；名额耗尽的瞬间，此后所有合成都会阻塞在获取处，
    # 连日志都打不出来（阻塞发生在进入引擎之前），上报线程随之卡死、
    # 「处理中」标记永不释放，表现为消息全哑、只能重启恢复。
    # 超时获取可保证「卡死的那次只丢它自己」，不牵连后续合成。
    acquired = _synth_sem.acquire(timeout=SYNTH_TIMEOUT)
    if not acquired:
        return False, "合成闸门等待超时（%d 秒），可能有合成卡死占用名额" % SYNTH_TIMEOUT
    try:
        errors = []
        for name in order:
            ok, err = _dispatch(name, text, out_path, voice, cfg)
            if ok:
                if len(order) > 1:
                    # 多引擎模式下记录实际生效的引擎，便于观察降级情况
                    log("语音合成成功：引擎=%s" % name)
                return True, ""
            # 每次失败单独落日志，便于定位是哪个引擎出的问题
            log("引擎 %s 失败：%s" % (name, err))
            errors.append("[%s] %s" % (name, err))
            # 失败时清掉可能残留的半成品，避免下次误判
            _safe_remove(out_path)
    finally:
        _synth_sem.release()

    return False, "；".join(errors) if errors else "所有语音引擎均失败"

# 音色清单（按引擎列举可选音色）在 voice_voices 模块，由调用方直接导入。
# 本模块不反向导入它：voice_voices 依赖本模块的配置读取与超时常量，
# 反向导入会形成循环，具体表现为从 voice_voices 一侧首次导入时失败。
