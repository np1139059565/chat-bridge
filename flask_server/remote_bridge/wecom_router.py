"""远程桥接 —— 企业微信推送路由

职责：
1. 处理抽屉上报，把新增消息推回企业微信
2. **发送图片与文件**（这是换用企业微信的核心理由）
3. 持久化 chatid，支持主动推送

与微信 ClawBot 推送的差异：
  ClawBot —— 配额紧张（每条用户消息约 10 条），必须整批合并；
             且图片发送未实现，截图只能回路径。
  企业微信 —— 主动推送无配额压力，可逐条发送；
             图片与文件都能真正发出去。

  但合并仍有价值：一轮对话里用户消息 + AI 回复 + 工具调用，
  逐条推会在手机上刷出很多条。故默认仍合并文本，
  但图片单独发（合并进文本就看不到图了）。
"""
import json
import os
import threading
import time

from . import bridge_store, bridge_log
from .message_parse import _classify


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][wecom]", *args)


# 会话键后缀：与 QQ / 微信的已推集合隔离，避免互相压制
# 单条消息最多发送的字符数
# 合并多条消息时的分隔线
# 各类消息的展示前缀
# 推送串行锁：同一会话的「读已推集合 → 发送 → 写回」必须整体串行
_lock = threading.RLock()

# 最近活跃的会话：{chatid: {chat_type, user, ts}}，供主动推送定位
_chats = {}


def note_chat(chatid, chat_type=1, user=""):
    """记录一个活跃会话，并持久化。

    企业微信的主动推送依赖 chatid；只存内存的话服务重启后就推不出去了。

    @param chatid    会话 id
    @param chat_type 1 单聊 / 2 群聊
    @param user      发送者
    """
    if not chatid:
        return
    with _lock:
        # 会话表按 chatid 覆盖更新，记录类型、发送者与最近活跃时间
        _chats[chatid] = {"chat_type": int(chat_type or 1),
                          "user": user or "", "ts": int(time.time())}
        # 复制快照用于落盘：锁外写盘，避免持锁做磁盘 IO
        snapshot = {k: dict(v) for k, v in _chats.items()}
    try:
        bridge_store.save_wecom_chats(snapshot)
    except Exception as e:
        log("持久化会话失败（不影响本次推送）：", e)


def _load_chats():
    """从磁盘恢复会话表（惰性，避免启动期读盘依赖）。

    @returns 会话表字典
    """
    global _chats
    with _lock:
        if _chats:
            return dict(_chats)
    try:
        data = bridge_store.load_wecom_chats() or {}
    except Exception as e:
        log("恢复会话失败：", e)
        data = {}
    with _lock:
        _chats.update(data)
        return dict(_chats)


def last_chat():
    """取最近活跃的会话：优先用持久化表，其次回退到最近用户。

    @returns (chatid, chat_type)；无则 ("", 1)
    """
    chats = _load_chats()
    if chats:
        # 按时间戳取最新
        cid = max(chats.items(), key=lambda kv: kv[1].get("ts", 0))[0]
        return cid, int(chats[cid].get("chat_type", 1))
    uid = bridge_store.load_last_wecom_user() or ""
    return uid, 1


# 出站媒体收集（图片落盘 / 文件下载 / 语音定位）已抽到 wecom_media_collect.py，
# 使本文件保持在行数上限内；此处按原名导入，保持既有调用不变。
from .wecom_media_collect import (  # noqa: E402
    collect_images as _collect_images,
    collect_files as _collect_files,
    collect_voice as _collect_voice_files,
)


