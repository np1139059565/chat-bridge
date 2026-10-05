"""AI 工具调用镜像插件 —— 全局日志

职责：给后端一个统一的日志落点，终端与文件双写、按天分文件、线程安全。
用于排查「接口卡死」这类问题：卡住时日志能还原「哪个请求、卡在哪一步」。

设计：
- 按天一个文件：data/logs/app-YYYY-MM-DD.log；
- 线程安全：请求线程、后台调度线程、桥接线程都会写，必须加锁防行交错；
- 写盘失败不影响主流程：日志是辅助，出错只吞掉、不抛异常；
- 分级：DEBUG / INFO / WARN / ERROR，阈值可调（默认 INFO）。

依赖：paths、threading、time、os
"""
import os
import threading
import time

import paths

# 写文件用的锁：保证同一时刻只有一个线程在写，行不交错
_write_lock = threading.Lock()

# 缓存当前日志文件的日期，跨天时自动换新文件
_current_day = ""

# 日志级别阈值：低于此级别的日志不输出。默认 INFO。
_LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}
_min_level = _LEVELS["INFO"]


def set_level(level):
    """设置最低输出级别。

    @param level 'DEBUG' / 'INFO' / 'WARN' / 'ERROR' 之一（大小写不敏感）
    """
    global _min_level
    lv = _LEVELS.get(str(level).upper())
    if lv is not None:
        _min_level = lv


def _day_str():
    """取当天日期字符串 YYYY-MM-DD。"""
    return time.strftime("%Y-%m-%d")


def _log_path(day):
    """拼出某天的日志文件路径。"""
    return os.path.join(str(paths.LOGS_DIR), "app-%s.log" % day)


def write(level, tag, *args):
    """写一条日志：终端 + 当天日志文件。

    @param level 级别字符串（DEBUG / INFO / WARN / ERROR）
    @param tag   日志前缀（如 [mem][save]），便于按模块过滤
    @param args  日志正文片段，用空格连接
    """
    global _current_day
    # 级别过滤：低于阈值的直接丢弃，避免刷屏
    if _LEVELS.get(str(level).upper(), 20) < _min_level:
        return
    # 正文：各片段转字符串后空格连接
    msg = " ".join(str(a) for a in args)
    # 行格式：时间 级别 标签 正文
    line = "%s %s %s %s" % (time.strftime("%H:%M:%S"), level, tag, msg)
    # 终端输出：保持实时可观察
    print(line, flush=True)
    # 文件输出：按天分文件，加锁写入
    try:
        os.makedirs(str(paths.LOGS_DIR), exist_ok=True)
        day = _day_str()
        with _write_lock:
            # 跨天时切换文件；文件不存在则追加模式自动创建
            if day != _current_day:
                _current_day = day
            with open(_log_path(day), "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        # 日志写盘失败不能影响主流程，静默吞掉
        pass


def debug(tag, *args):
    """写 DEBUG 级日志。"""
    write("DEBUG", tag, *args)


def info(tag, *args):
    """写 INFO 级日志。"""
    write("INFO", tag, *args)


def warn(tag, *args):
    """写 WARN 级日志。"""
    write("WARN", tag, *args)


def error(tag, *args):
    """写 ERROR 级日志。"""
    write("ERROR", tag, *args)
