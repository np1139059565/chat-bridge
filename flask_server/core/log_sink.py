"""日志落盘公共辅助 —— 按天分文件的追加写入

职责：把「按天分文件 + 追加写入 + 跨天切换 + 失败静默」这段逻辑集中一处，
供 app_log（全局异步日志）与 bridge_log（桥接同步日志）共用，
避免两处各写一份实现，日后修改行为时只需改这里。

设计要点：
- 每个 sink 绑定一个文件名前缀（如 app / bridge）与一个目录提供者；
- 目录提供者在每次写入时动态取值，便于测试重定向 paths.LOGS_DIR；
- 写入加锁，保证多线程下同一行不被拆散；
- 写盘失败只吞掉、不抛异常：日志是辅助，不能影响主流程。

依赖：os、threading、time
"""
import os
import threading
import time


def day_str():
    """取当天日期字符串 YYYY-MM-DD。"""
    # 以本地时间格式化当天日期，作为日志文件名后缀
    return time.strftime("%Y-%m-%d")


class DayFileSink:
    """按天分文件的日志落盘器。

    一个实例对应一类日志（由文件名前缀区分），例如 app-2026-01-01.log。
    实例内部维护「当前日期」缓存，跨天时自动切到新文件。
    """

    def __init__(self, prefix, dir_provider):
        """构造落盘器。

        @param prefix       文件名前缀（如 "app" / "bridge"）
        @param dir_provider 无参可调用对象，返回日志目录字符串；每次写入时调用，
                            以便外部（如测试）重定向目录后立即生效
        """
        # 记录前缀，用于拼出「前缀-日期.log」
        self._prefix = prefix
        # 记录目录提供者，写入时动态取值
        self._dir_provider = dir_provider
        # 写文件用的锁：保证同一时刻只有一个线程在写，行不交错
        self._lock = threading.Lock()
        # 缓存当前日志文件的日期，跨天时自动换新文件（仅写锁内读写）
        self._current_day = ""

    def _log_path(self, day):
        """拼出某天的日志文件路径。

        @param day 日期字符串 YYYY-MM-DD
        @returns 完整文件路径字符串
        """
        # 目录每次从 provider 取，保证重定向生效；文件名用「前缀-日期.log」
        return os.path.join(str(self._dir_provider()), "%s-%s.log" % (self._prefix, day))

    def append(self, line):
        """追加一行日志到当天文件。

        目录不存在则创建；跨天则切换文件；写盘失败静默吞掉。
        @param line 已格式化好的日志行（不含换行符）
        """
        try:
            # 确保日志目录存在（首次写入或目录被清理时创建）
            os.makedirs(str(self._dir_provider()), exist_ok=True)
            # 取当天日期，用于判断是否需要切换文件
            day = day_str()
            # 加锁：保证「判断跨天 + 打开 + 写入」这段临界区不被并发打断
            with self._lock:
                # 跨天时更新缓存日期（新文件由追加模式自动创建）
                if day != self._current_day:
                    self._current_day = day
                # 追加模式写入，末尾补换行，保证一行一条
                with open(self._log_path(day), "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception:
            # 日志写盘失败不能影响主流程，静默吞掉
            pass
