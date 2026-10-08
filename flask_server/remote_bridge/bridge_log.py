"""远程桥接 —— 日志落盘（异步）

职责：把桥接层的运行日志既打到终端、又按天写入文件，
让运行轨迹有迹可循（后端 print 默认只进终端，重启即丢）。

设计：
- 按天一个文件：data/logs/bridge-YYYY-MM-DD.log。
- 异步写盘：write 只入队即返回，由单个后台线程消费落盘。
  桥接层在 WebSocket 回调线程、Flask 请求线程、语音后台线程里都会写日志，
  若同步落盘，磁盘繁忙时会阻塞这些线程；异步化后写入方不被磁盘拖住。
- 队列有界：消费跟不上时丢弃最旧一条，兜住内存。
- 写入失败不影响主流程：日志是辅助，出错只吞掉，不抛异常。
"""
import time

import paths
import log_sink

# 异步落盘器：入队即返回，单后台线程消费；有界队列，满时丢最旧。
# 目录每次写入时动态取，便于测试重定向 paths.LOGS_DIR 后立即生效。
_sink = log_sink.AsyncDayFileSink("bridge", lambda: paths.LOGS_DIR)


def write(tag, *args):
    """写一条日志：入队即返回，由后台线程打印 + 落盘。

    @param tag  日志前缀（如 [bridge][gateway]）
    @param args 日志正文片段，用空格连接
    """
    # 正文：各片段转字符串后空格连接
    msg = " ".join(str(a) for a in args)
    line = "%s %s %s" % (time.strftime("%H:%M:%S"), tag, msg)
    # 入队即返回；后台线程负责终端打印与落盘
    _sink.write(line)


def drain(timeout=3.0):
    """等待队列中的日志全部落盘（供退出或测试使用）。"""
    return _sink.drain(timeout)
