"""远程桥接 —— 日志落盘

职责：把桥接层的运行日志既打到终端、又按天写入文件，
让运行轨迹有迹可循（后端 print 默认只进终端，重启即丢）。

设计：
- 按天一个文件：data/logs/bridge-YYYY-MM-DD.log。
- 线程安全：桥接层在 WebSocket 回调线程、Flask 请求线程、
  语音后台线程里都会写日志，必须加锁，避免行内容交错。
- 写入失败不影响主流程：日志是辅助，出错只吞掉，不抛异常。
"""
import time

import paths
import log_sink

# 日志落盘器：按天分文件、加锁追加、失败静默。目录每次写入时动态取，
# 便于测试重定向 paths.LOGS_DIR 后立即生效。
_sink = log_sink.DayFileSink("bridge", lambda: paths.LOGS_DIR)


def write(tag, *args):
    """写一条日志：终端 + 当天日志文件。

    @param tag  日志前缀（如 [bridge][gateway]）
    @param args 日志正文片段，用空格连接
    """
    # 正文：各片段转字符串后空格连接
    msg = " ".join(str(a) for a in args)
    line = "%s %s %s" % (time.strftime("%H:%M:%S"), tag, msg)
    # 终端输出：保持既有行为，便于开发时实时观察
    print(line)
    # 文件输出：交给公共落盘器（按天分文件、加锁、失败静默）
    _sink.append(line)
