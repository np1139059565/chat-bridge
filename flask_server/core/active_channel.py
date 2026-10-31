"""AI 工具调用镜像插件 —— 最近活跃客户端登记

职责：记录「最后一个给机器人发消息的客户端」（QQ / 网页），
供文件推送等主动下发能力决定往哪边投。

背景：push_file 此前只认 QQ（取最近一次 QQ 交互的客户端与用户号），
网页版调用时必然报「远程桥接尚未就绪」。而下发目标本就该跟着
「最后跟机器人说话的那个人」走：谁刚发消息，产物就推回谁那里。

设计：进程内单值 + 锁。只记渠道名，不重复存各渠道自身的句柄：
QQ 的客户端引用与被动回复窗口仍由 message_router 维护，
网页的消息则由 web_inbox 承载。本模块只回答「往哪边推」这一个问题。
"""
import threading

# 保护 _channel 的互斥锁：登记与读取可能发生在不同请求线程
_lock = threading.Lock()

# 最近活跃渠道："qq" / "web"；空串表示尚无任何客户端发过消息
_channel = ""

# 允许登记的渠道名：白名单校验，避免写入拼错的值导致下发逻辑失效
_CHANNELS = ("qq", "web")


def note(channel):
    """登记某渠道刚收到一条用户消息（含 /h 这类指令）。

    @param channel "qq" 或 "web"；其它值一律忽略，防止脏状态
    """
    global _channel
    # 非法渠道名直接丢弃：宁可保持原状态，也不写入无法识别的值
    if channel not in _CHANNELS:
        return
    with _lock:
        _channel = channel


def get():
    """取最近活跃渠道；尚无记录时返回空串。

    @returns "qq" / "web" / ""
    """
    with _lock:
        return _channel


def is_web():
    """最近活跃客户端是否为网页版。

    供下发逻辑做分支：True 走网页下载链接，False 走 QQ 推送。
    """
    return get() == "web"


def reset_for_tests():
    """测试专用：清空登记，使后续判定回到「尚无记录」状态。"""
    global _channel
    with _lock:
        _channel = ""
