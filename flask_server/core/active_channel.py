"""AI 工具调用镜像插件 —— 最近活跃客户端登记

职责：记录「最后一个给机器人发消息的客户端」（QQ / 网页），
供文件推送等主动下发能力决定往哪边投。

背景：push_file 此前只认 QQ（取最近一次 QQ 交互的客户端与用户号），
网页版调用时必然报「远程桥接尚未就绪」。而下发目标本就该跟着
「最后跟机器人说话的那个人」走：谁刚发消息，产物就推回谁那里。

设计：进程内单值 + 锁，并落盘一份到运行时数据目录。
只记渠道名，不重复存各渠道自身的句柄：
QQ 的客户端引用与被动回复窗口仍由 message_router 维护，
网页的消息则由 web_inbox 承载。本模块只回答「往哪边推」这一个问题。

落盘的必要性：渠道只存内存时，服务重启后归零，
此时用户在网页会话里直接调 push_file 会被判成非网页、走 QQ 分支，
误报「远程桥接尚未就绪」。落盘后重启即恢复，行为与重启前一致。

依赖：threading、paths、app_log
"""
import threading

import paths
import app_log

# 保护 _channel 的互斥锁：登记与读取可能发生在不同请求线程
_lock = threading.Lock()

# 最近活跃渠道："qq" / "web"；空串表示尚无任何客户端发过消息
_channel = ""

# 允许登记的渠道名：白名单校验，避免写入拼错的值导致下发逻辑失效
_CHANNELS = ("qq", "web")

# 落盘文件：与桥接状态同目录，属运行时产物，不入库
_STATE_PATH = paths.DATA_DIR / "active_channel.txt"

# 是否已尝试过从磁盘恢复：只做一次，避免每次读取都碰磁盘
_loaded = False


def _load_once():
    """首次使用时从磁盘恢复渠道（仅一次）。

    读取失败一律按「尚无记录」处理：这是可重建的运行时状态，
    宁可退回空值，也不能因读文件失败让整个下发能力不可用。
    """
    global _channel, _loaded
    if _loaded:
        return
    _loaded = True
    try:
        v = _STATE_PATH.read_text(encoding="utf-8").strip()
        # 只接受白名单内的值：文件被手工改坏时不把脏值带进内存
        if v in _CHANNELS:
            _channel = v
    except FileNotFoundError:
        # 首次运行、尚无记录：保持空值即可，不视为错误
        pass
    except Exception as e:
        app_log.warn("[channel]", "恢复最近活跃渠道失败（按无记录处理）：%s" % e)


def _persist(channel):
    """把渠道写入磁盘（调用方已持锁）。

    写失败只告警、不抛出：渠道是「下次推给谁」的提示，
    丢一次最多让下次下发走默认分支，不应让发消息的主流程失败。
    @param channel 已通过白名单校验的渠道名
    """
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(channel, encoding="utf-8")
    except Exception as e:
        app_log.warn("[channel]", "保存最近活跃渠道失败：%s" % e)


def note(channel):
    """登记某渠道刚收到一条用户消息（含 /h 这类指令）。

    登记后立即落盘：进程重启后仍能知道「最后是谁在说话」。
    @param channel "qq" 或 "web"；其它值一律忽略，防止脏状态
    """
    global _channel
    # 非法渠道名直接丢弃：宁可保持原状态，也不写入无法识别的值
    if channel not in _CHANNELS:
        return
    with _lock:
        _channel = channel
        _persist(channel)


def get():
    """取最近活跃渠道；尚无记录时返回空串。

    @returns "qq" / "web" / ""
    """
    _load_once()
    with _lock:
        return _channel


def is_web():
    """最近活跃客户端是否为网页版。

    供下发逻辑做分支：True 走网页下载链接，False 走 QQ 推送。
    """
    return get() == "web"


def reset_for_tests():
    """测试专用：清空内存与磁盘记录，使判定回到「尚无记录」状态。"""
    global _channel, _loaded
    with _lock:
        _channel = ""
        _loaded = True   # 置为已加载，避免随后 get() 又把磁盘上的旧值读回来
        try:
            _STATE_PATH.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass
