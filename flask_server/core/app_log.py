"""AI 工具调用镜像插件 —— 全局日志（异步写盘）

职责：给后端一个统一的日志落点，终端与文件双写、按天分文件、线程安全。
用于排查「接口卡死」这类问题：卡住时日志能还原「哪个请求、卡在哪一步」。

设计（异步写盘）：
- 调用方（请求线程 / 后台线程 / 桥接线程）调 write 只做「级别过滤 + 入队」，
  随即返回，不做任何磁盘 IO、不抢全局锁；
- 单个后台守护线程消费队列，负责终端打印与落盘；
- 队列 FIFO + 单消费者 → 日志顺序与入队顺序一致；
- drain(timeout) 可等待队列排空，供进程正常退出或测试时确保不丢日志；
- 写盘失败不影响主流程：日志是辅助，出错只吞掉、不抛异常；
- 分级：DEBUG / INFO / WARN / ERROR，阈值可调（默认 INFO）。

依赖：paths、queue、threading、time、os
"""
import queue
import threading
import time

import paths
import log_sink

# 日志级别阈值：低于此级别的日志不输出。默认 INFO。
_LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}
_min_level = _LEVELS["INFO"]

# 日志行队列：写入方只入队，后台线程消费。无界队列，避免写入方被阻塞。
_queue = queue.Queue()

# 后台写线程的启动标志与保护锁（仅用于「只启动一次」）。
_worker_started = False
_worker_lock = threading.Lock()


def set_level(level):
    """设置最低输出级别。

    @param level 'DEBUG' / 'INFO' / 'WARN' / 'ERROR' 之一（大小写不敏感）
    """
    global _min_level
    lv = _LEVELS.get(str(level).upper())
    if lv is not None:
        _min_level = lv


# 日志落盘器：按天分文件、加锁追加、失败静默。目录每次写入时动态取，
# 便于测试重定向 paths.LOGS_DIR 后立即生效。
_sink = log_sink.DayFileSink("app", lambda: paths.LOGS_DIR)


def _worker():
    """后台消费线程：从队列取日志行，打印到终端并追加落盘。

    循环永不退出（守护线程，进程结束即止）。每条处理完调用 task_done，
    供 drain 判断「是否已全部落盘」。
    """
    while True:
        # 阻塞取一条；队列空时在此挂起，不占用 CPU
        line = _queue.get()
        try:
            # 终端输出：保持实时可观察（放在消费端，写入方不必等终端）
            try:
                print(line, flush=True)
            except Exception:
                pass
            # 文件输出：交给公共落盘器（按天分文件、加锁、失败静默）
            _sink.append(line)
        finally:
            # 无论成败都标记该条已处理，保证 drain 能正常判定
            _queue.task_done()


def _ensure_worker():
    """确保后台写线程已启动（幂等：重复调用只启动一次）。"""
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        t = threading.Thread(target=_worker, daemon=True, name="app_log")
        t.start()
        _worker_started = True


def write(level, tag, *args):
    """写一条日志：级别过滤后入队，由后台线程打印 + 落盘。

    本函数不做磁盘 IO、不抢锁，调用方（请求线程）能立即返回。
    @param level 级别字符串（DEBUG / INFO / WARN / ERROR）
    @param tag   日志前缀（如 [mem][save]），便于按模块过滤
    @param args  日志正文片段，用空格连接
    """
    # 级别过滤：低于阈值的直接丢弃，避免刷屏
    if _LEVELS.get(str(level).upper(), 20) < _min_level:
        return
    # 正文：各片段转字符串后空格连接
    msg = " ".join(str(a) for a in args)
    # 行格式：时间 级别 标签 正文（时间取入队时刻，反映真实发生时间）
    line = "%s %s %s %s" % (time.strftime("%H:%M:%S"), level, tag, msg)
    # 入队即返回；后台线程负责实际输出
    _queue.put(line)


def drain(timeout=3.0):
    """等待队列中的日志全部被消费（落盘）。

    用于进程正常退出或测试时，确保已入队的日志不丢失。
    @param timeout 最长等待秒数
    @returns 是否已排空（True 表示全部处理完）
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _queue.unfinished_tasks == 0:
            return True
        time.sleep(0.005)
    return _queue.unfinished_tasks == 0


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


# 模块导入即启动后台写线程，保证首次 write 前消费端已就绪
_ensure_worker()
