"""远程桥接 —— 企业微信活跃会话表

问题背景：
    企业微信的主动推送依赖 chatid，它是「会话」标识而非「用户」标识：
    单聊与群聊各有自己的 chatid，同一个人的两个群也是两个 chatid。
    因此这条通道不能像 QQ / 微信那样只记「最近一个用户」，
    必须记住「最近活跃的会话」，并保存会话类型（1 单聊 / 2 群聊）。

为什么必须持久化：
    只存内存时，服务重启后会话表为空，主动推送找不到 chatid 就发不出去。
    落盘后重启即可续用，直到用户下次发消息刷新。

与 target.py 的分工：
    target.py 记「最近跟我说话的人」，用于兜底；
    本模块记「最近活跃的会话」，用于精确定位。
    两者互补：有会话表时优先用会话，没有时回退到用户兜底。
"""
import threading
import time

from .. import bridge_store
from . import target

# 会话表：{ chatid: {chat_type, user, ts} }
# 进程内唯一一份，避免各处各存一份导致状态不一致。
_chats = {}

# 保护 _chats 的锁：收消息与取目标可能并发。
_lock = threading.RLock()


def clear():
    """清空内存会话表。

    供测试隔离使用；正常运行中不应调用，否则会丢掉推送目标
    （重启后可从磁盘恢复，但内存中尚未落盘的部分会丢失）。
    """
    with _lock:
        _chats.clear()


def note(chatid, chat_type=1, user=""):
    """登记一个活跃会话，并立即落盘。

    同一 chatid 重复登记只更新，不新增条目——它代表的是同一个会话，
    更新的是「最后一次活跃时间」与发送者。

    @param chatid    会话 id；空值不登记
    @param chat_type 1 单聊 / 2 群聊
    @param user      发送者标识
    """
    # 空 chatid 直接忽略：避免一次无标识的事件污染会话表
    if not chatid:
        return
    with _lock:
        # 按 chatid 覆盖更新：类型、发送者、最近活跃时间
        _chats[chatid] = {"chat_type": int(chat_type or 1),
                          "user": user or "",
                          "ts": int(time.time())}
        # 复制快照用于落盘：锁外写盘，避免持锁做磁盘 IO
        snapshot_data = {k: dict(v) for k, v in _chats.items()}
    try:
        # 落盘失败不影响本次推送：内存值仍可用于本轮
        bridge_store.save_wecom_chats(snapshot_data)
    except Exception:
        pass


def _ensure_loaded():
    """惰性从磁盘恢复会话表。

    惰性而非模块导入时恢复：导入发生在服务启动早期，
    此时配置与路径层可能尚未就绪，读盘会引入启动顺序依赖。
    """
    with _lock:
        # 已有内存数据就不再读盘，避免覆盖较新的值
        if _chats:
            return
    try:
        data = bridge_store.load_wecom_chats() or {}
    except Exception:
        data = {}
    with _lock:
        # 双重检查：读盘期间可能有其它线程写入，不能覆盖
        if not _chats and data:
            _chats.update(data)


def snapshot():
    """取会话表的浅拷贝，供读取方遍历而不影响内部状态。

    @returns 会话表字典的副本
    """
    _ensure_loaded()
    with _lock:
        # 每个条目也复制一份，避免调用方改动值里的字典
        return {k: dict(v) for k, v in _chats.items()}


def last():
    """取最近活跃的会话。

    优先用会话表里时间戳最新的；会话表为空时回退到「最近用户」兜底。

    @returns (chatid, chat_type)；无任何记录时返回 ("", 1)
    """
    chats = snapshot()
    if chats:
        # 按 ts 取最大值：就是最后说话的那个会话
        cid = max(chats.items(), key=lambda kv: kv[1].get("ts", 0))[0]
        return cid, int(chats[cid].get("chat_type", 1))
    # 会话表为空：用最近用户兜底，按单聊处理
    return target.wecom.get(), 1
