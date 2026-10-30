"""远程桥接 —— 被动回复窗口的持久化

背景：
窗口（openid → msg_id + 序号 + 过期时间）此前只存内存，进程一重启就全丢，
用户必须重新发消息才能继续收到推送。这不符合直觉：窗口本身有 60 分钟有效期，
重启不该让一个尚未过期的窗口作废。

为什么必须连序号一起存（关键）：
QQ 按 (msg_id, msg_seq) 去重，重复的组合会被静默丢弃（错误码 40054005）。
若只恢复 msg_id 而序号从 1 重数，重启后的每条推送都会撞上重启前已用过的序号，
表现为「接口返回成功但手机上收不到」——比不恢复更糟。故 msg_id、seq、expire
三者必须作为一个整体存取。

淘汰规则（与内存窗口一致）：
- 载入时丢弃已过期的窗口；
- 同一 openid 出现更新的 msg_id 时，旧的被覆盖（一个用户只保留最近一个窗口）。

落盘时机：每次窗口新建 / 续期 / 序号自增后写入，频率与人发消息相当，开销可忽略。
"""
import json
import os
import threading
import time

import paths

# 保护读写文件的锁：桥接回调线程与 Flask 请求线程可能同时触发写盘
_lock = threading.Lock()


def _path():
    """取窗口存盘文件路径（延迟读，便于测试替换）。"""
    return str(paths.BRIDGE_WINDOWS_PATH)


def load():
    """从磁盘载入窗口表，丢弃已过期项。

    @returns { openid: {"msg_id", "seq", "expire"} }；文件缺失或损坏时返回空表
    """
    p = _path()
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f) or {}
    except Exception:
        # 文件损坏不应让服务起不来：当作没有历史窗口，等用户下条消息重建
        return {}
    now = time.time()
    out = {}
    for openid, w in raw.items():
        if not isinstance(w, dict):
            continue
        # 过期窗口一律丢弃：QQ 侧已不接受该 msg_id 的被动回复
        if float(w.get("expire") or 0) <= now:
            continue
        if not w.get("msg_id"):
            continue
        out[str(openid)] = {
            "msg_id": str(w.get("msg_id")),
            "seq": int(w.get("seq") or 0),
            "expire": float(w.get("expire") or 0),
        }
    return out


def save_windows(windows):
    """对窗口表做快照后写盘（供调用方在锁外调用）。

    先复制一份再写：调用方可能在锁内传引用，写盘期间其它线程仍在改动原表，
    直接序列化会读到半新半旧的状态甚至触发「字典改变大小」异常。
    @param windows 内存中的窗口表
    @returns 是否写成功
    """
    return save({k: dict(v) for k, v in windows.items()})


def save(windows):
    """把窗口表整体写盘（先写临时文件再替换，避免写一半崩溃留下坏文件）。

    @param windows { openid: {"msg_id", "seq", "expire"} }
    @returns 是否写成功
    """
    p = _path()
    with _lock:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(windows, f, ensure_ascii=False, indent=2)
            os.replace(tmp, p)
            return True
        except Exception:
            # 存盘失败不影响推送主流程：内存窗口仍然可用，只是重启后会丢
            return False
