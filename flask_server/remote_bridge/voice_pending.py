"""远程桥接 —— 待确认语音文字暂存

职责：语音经 ASR 转成文字后，先暂存，等用户发 /vo 确认再投给 AI。

设计（按用户要求）：
- **不排队**：新语音过来直接覆盖旧的，只保留最近一条。
- 按 openid 隔离：每个用户各存一份自己的待确认文字。
- 带过期时间：超时未确认自动失效，避免隔很久才 /vo 把陈旧内容投给 AI。

为什么只留最近一条：语音是即时对话场景，排队会积压，
用户又看不到队列，确认时反而不知道确认的是哪条。只留最新最符合直觉。
"""
import threading
import time

# 待确认文字的存活时长（秒）：超过则视为过期，/vo 时取不到
PENDING_TTL = 10 * 60

_lock = threading.Lock()

# { openid: {"text": 文字, "expire": 过期时间戳, "msg_id": 原语音消息 id} }
_pending = {}


def stash(openid, text, msg_id=""):
    """暂存一条待确认文字，覆盖该用户旧的待确认内容。

    @param openid 用户标识
    @param text   ASR 识别出的文字
    @param msg_id 原语音消息 id（确认后投递时可能要用）
    """
    with _lock:
        _pending[openid] = {
            "text": text,
            "expire": time.time() + PENDING_TTL,
            "msg_id": msg_id,
        }


def take(openid):
    """取出并清除该用户的待确认文字；无或已过期返回 None。

    /vo 确认时调用：取到即消费掉，避免重复投递。
    @returns 文字字符串；无待确认内容返回 None
    """
    with _lock:
        item = _pending.pop(openid, None)
    if not item:
        return None
    if time.time() >= item.get("expire", 0):
        return None       # 已过期：视为不存在
    return item.get("text") or ""


def peek(openid):
    """查看该用户是否有待确认文字（不消费）；有返回 True。"""
    with _lock:
        item = _pending.get(openid)
    if not item:
        return False
    return time.time() < item.get("expire", 0)


def clear(openid):
    """清除该用户的待确认文字（丢弃时调用）。"""
    with _lock:
        _pending.pop(openid, None)
