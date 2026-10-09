"""日志落盘公共辅助 —— 按天分文件 + 异步写入器

职责：把「按天分文件 + 追加写入 + 跨天切换 + 失败静默」集中一处，
供 app_log（全局异步日志）、bridge_log（桥接日志）、client_log（前端上报）共用，
避免各处各写一份实现。

提供两个类：
- DayFileSink：同步落盘器，缓存文件句柄（减少每条日志的开合开销）；
- AsyncDayFileSink：异步落盘器，写入方入队即返回，单后台线程消费，
  有界队列 + 满时丢最旧，避免消费跟不上导致内存无界增长。

设计要点：
- 目录提供者在每次写入时动态取值，便于测试重定向 paths.LOGS_DIR；
- 写入加锁，保证多线程下同一行不被拆散；
- 写盘失败只吞掉、不抛异常：日志是辅助，不能影响主流程。

依赖：os、queue、threading、time
"""
import os
import queue
import threading
import time


# 异步队列默认容量取自全项目统一来源（app_limits）：满时丢弃最旧的一条。
# 取值足够大，正常流量下不会触及；异常堆积时兜住内存。
from app_limits import LOG_QUEUE_MAX as DEFAULT_QUEUE_MAX


def day_str():
    """取当天日期字符串 YYYY-MM-DD。"""
    # 以本地时间格式化当天日期，作为日志文件名后缀
    return time.strftime("%Y-%m-%d")


class DayFileSink:
    """按天分文件的日志落盘器（缓存当前文件句柄）。

    一个实例对应一类日志（由文件名前缀区分），例如 app-2026-01-01.log。
    缓存「目录 + 日期」对应的文件句柄：只要目录与日期不变就复用，
    避免每条日志都 open/close 一次；跨天或目录变化时自动切换。

    注意：缓存句柄意味着「当天的日志文件」在运行期间被本进程持有，
    Windows 下无法删除该文件；这是为减少开合开销付出的代价。
    历史日期（非当天）的文件在切换时即被关闭并释放。
    """

    def __init__(self, prefix, dir_provider):
        """构造落盘器。

        @param prefix       文件名前缀（如 "app" / "bridge" / "client"）
        @param dir_provider 无参可调用对象，返回日志目录字符串；每次写入时调用，
                            以便外部（如测试）重定向目录后立即生效
        """
        # 记录前缀，用于拼出「前缀-日期.log」
        self._prefix = prefix
        # 记录目录提供者，写入时动态取值
        self._dir_provider = dir_provider
        # 写文件用的锁：保证同一时刻只有一个线程在写，行不交错
        self._lock = threading.Lock()
        # 缓存的句柄与它对应的键 (目录, 日期)；键变化时重开
        self._fh = None
        self._fh_key = None

    def _log_path(self, directory, day):
        """拼出某天的日志文件路径。

        @param directory 日志目录
        @param day       日期字符串 YYYY-MM-DD
        @returns 完整文件路径字符串
        """
        return os.path.join(str(directory), "%s-%s.log" % (self._prefix, day))

    def _ensure_open(self, directory, day, key):
        """确保句柄指向 (目录, 日期) 对应的文件；不一致则切换。

        @param directory 日志目录
        @param day       日期字符串
        @param key       (目录, 日期) 元组，用于判断是否需要切换
        """
        if self._fh is not None and self._fh_key == key:
            return
        # 关闭旧句柄（跨天或目录变化），再开新文件
        self._close_locked()
        os.makedirs(str(directory), exist_ok=True)
        self._fh = open(self._log_path(directory, day), "a", encoding="utf-8")
        self._fh_key = key

    def _close_locked(self):
        """关闭当前句柄（须在锁内调用）；失败静默。"""
        if self._fh is not None:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None
            self._fh_key = None

    def append(self, line):
        """追加一行日志到当天文件。

        目录不存在则创建；跨天或目录变化则切换文件；写盘失败静默吞掉。
        @param line 已格式化好的日志行（不含换行符）
        """
        try:
            directory = str(self._dir_provider())
            day = day_str()
            key = (directory, day)
            # 加锁：保证「判断切换 + 打开 + 写入」这段临界区不被并发打断
            with self._lock:
                self._ensure_open(directory, day, key)
                self._fh.write(line + "\n")
                # 每条即刷：保证进程崩溃时已写日志尽量落盘（与旧行为一致）
                self._fh.flush()
        except Exception:
            # 日志写盘失败不能影响主流程，静默吞掉
            pass

    def close(self):
        """关闭缓存句柄，释放文件（供退出或测试清理调用）。"""
        with self._lock:
            self._close_locked()


class AsyncDayFileSink:
    """异步落盘器：写入方入队即返回，单后台线程消费落盘。

    用途：把日志写入从调用线程剥离。调用方（请求线程 / 回调线程 / 语音线程）
    调 write 只做入队，随即返回，不做磁盘 IO，不因磁盘繁忙而被阻塞。

    - 有界队列 + 满时丢弃最旧：消费跟不上时兜住内存，不无界增长；
    - drain(timeout)：等待队列排空，供进程退出或测试使用；
    - also_print：是否同时打印到终端（开发时可观察）。
    """

    def __init__(self, prefix, dir_provider, maxsize=DEFAULT_QUEUE_MAX, also_print=True):
        """构造异步落盘器。

        @param prefix       文件名前缀
        @param dir_provider 日志目录提供者
        @param maxsize      队列容量上限（满时丢最旧）
        @param also_print   是否同时打印到终端
        """
        # 底层同步落盘器
        self._sink = DayFileSink(prefix, dir_provider)
        # 有界队列：满时写入方负责丢最旧
        self._queue = queue.Queue(maxsize=maxsize)
        self._also_print = also_print
        # 丢弃计数：便于观察是否发生过丢弃
        self._dropped = 0
        self._dropped_lock = threading.Lock()
        # 后台线程惰性启动（首次写入时），避免无日志时也占线程
        self._started = False
        self._start_lock = threading.Lock()

    def _ensure_worker(self):
        """确保后台消费线程已启动（幂等）。"""
        with self._start_lock:
            if self._started:
                return
            t = threading.Thread(target=self._worker, daemon=True, name="log_sink")
            t.start()
            self._started = True

    def _worker(self):
        """后台消费线程：取日志行，可选打印，然后落盘。永不退出（守护线程）。"""
        while True:
            line = self._queue.get()
            try:
                if self._also_print:
                    try:
                        print(line, flush=True)
                    except Exception:
                        pass
                self._sink.append(line)
            finally:
                # 无论成败都标记已处理，保证 drain 能正常判定
                self._queue.task_done()

    def write(self, line):
        """入队一行日志，立即返回；队列满时丢弃最旧一条。

        @param line 已格式化好的日志行（不含换行符）
        """
        self._ensure_worker()
        try:
            self._queue.put_nowait(line)
            return
        except queue.Full:
            pass
        # 队列满：丢最旧一条腾位。被丢的记为「已处理」，否则 drain 会一直等它。
        try:
            self._queue.get_nowait()
            self._queue.task_done()
            with self._dropped_lock:
                self._dropped += 1
        except queue.Empty:
            pass
        # 再尝试放入本次这条；仍满则放弃（极端情况）
        try:
            self._queue.put_nowait(line)
        except queue.Full:
            pass

    def drain(self, timeout=3.0):
        """等待队列中的日志全部被消费（落盘）。

        @param timeout 最长等待秒数
        @returns 是否已排空（True 表示全部处理完）
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.005)
        return self._queue.unfinished_tasks == 0

    def dropped(self):
        """返回因队列满被丢弃的日志条数。"""
        with self._dropped_lock:
            return self._dropped

    def close(self):
        """关闭底层落盘器的缓存句柄。"""
        self._sink.close()
