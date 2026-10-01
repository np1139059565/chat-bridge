"""远程桥接 —— 日志落盘

职责：把桥接层的运行日志既打到终端、又按天写入文件，
让运行轨迹有迹可循（后端 print 默认只进终端，重启即丢）。

设计：
- 按天一个文件：data/logs/bridge-YYYY-MM-DD.log。
- 线程安全：桥接层在 WebSocket 回调线程、Flask 请求线程、
  语音后台线程里都会写日志，必须加锁，避免行内容交错。
- 写入失败不影响主流程：日志是辅助，出错只吞掉，不抛异常。
"""
import os
import threading
import time

import paths

# 写文件用的锁：保证同一时刻只有一个线程在写，行不交错
_write_lock = threading.Lock()

# 缓存当前日志文件的日期，跨天时自动换新文件
_current_day = ""


def _day_str():
    """取当天日期字符串 YYYY-MM-DD。"""
    return time.strftime("%Y-%m-%d")


def _log_path(day):
    """拼出某天的日志文件路径。"""
    return os.path.join(str(paths.LOGS_DIR), "bridge-%s.log" % day)


def write(tag, *args):
    """写一条日志：终端 + 当天日志文件。

    @param tag  日志前缀（如 [bridge][gateway]）
    @param args 日志正文片段，用空格连接
    """
    global _current_day
    # 正文：各片段转字符串后空格连接
    msg = " ".join(str(a) for a in args)
    line = "%s %s %s" % (time.strftime("%H:%M:%S"), tag, msg)
    # 终端输出：保持既有行为，便于开发时实时观察
    print(line)
    # 文件输出：按天分文件，加锁写入
    try:
        os.makedirs(str(paths.LOGS_DIR), exist_ok=True)
        day = _day_str()
        with _write_lock:
            # 跨天时切换文件；文件不存在则新建（追加模式自动创建）
            if day != _current_day:
                _current_day = day
            with open(_log_path(day), "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        # 日志写盘失败不能影响主流程，静默吞掉
        pass
