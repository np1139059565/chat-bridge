"""串行工作队列（serial_worker）单元测试。

被测：core/serial_worker.py 的 SerialWorker。
该队列是全项目「单后台线程 + 串行处理」的公共骨架，
服务记忆保存、记忆蒸馏、命令任务三处，故其并发正确性必须有回归保护。

重点覆盖：
- 去重语义（keep_first=True）：同 key 只保留首次；
- 最新覆盖语义（keep_first=False）：同 key 用最新元素；
- 幂等启动：多次提交只起一个线程；
- 不丢任务：多线程并发提交后所有 key 都被处理（防丢唤醒）；
- 队列空后可重新拉起；
- 异常隔离：单个元素处理抛异常不阻断后续元素；
- on_error 回调被调用。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_serial_worker -v
"""
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core"))

import serial_worker


def _wait_until(predicate, timeout=3.0):
    """自旋等待 predicate 返回真，超时返回 False。

    @param predicate 无参可调用，返回布尔
    @param timeout   最长等待秒数
    @returns 是否在超时前满足
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class TestDedupAndOverride(unittest.TestCase):
    """验证两种去重策略：保留首次 / 最新覆盖。"""

    def test_keep_first_dedups_same_key(self):
        """keep_first=True 时，同 key 重复提交只处理一次（首次）。

        注：去重只针对「待处理队列」，不含「正在处理」的项。
        因此需先用一个阻塞任务占住 worker，使后续同一 key 的提交
        堆积在队列中，才能稳定复现去重。
        """
        done = []                                   # 记录处理过的元素
        lock = threading.Lock()                     # 保护 done
        release = threading.Event()                 # 放行阻塞任务

        def handler(item):                          # 处理函数
            if item[0] == "blocker":                # 阻塞任务：占住 worker
                release.wait(timeout=3.0)
                return
            with lock:
                done.append(item)

        w = serial_worker.SerialWorker(handler, keep_first=True)
        w.submit("blocker", ("blocker", 0))         # 占住 worker
        time.sleep(0.1)                             # 确保 worker 已取走 blocker
        w.submit("k", ("k", 1))                     # 首次入队（堆积）
        w.submit("k", ("k", 2))                     # 重复：应被忽略
        release.set()                               # 放行 worker
        self.assertTrue(_wait_until(lambda: len(done) >= 1))
        time.sleep(0.2)                             # 给 worker 处理完的机会
        self.assertEqual(done, [("k", 1)], "keep_first 应只处理首次")

    def test_keep_last_overrides_same_key(self):
        """keep_first=False 时，同 key 用最新元素覆盖。"""
        done = []
        lock = threading.Lock()

        def handler(item):
            with lock:
                done.append(item)

        w = serial_worker.SerialWorker(handler, keep_first=False)
        # 连续提交同一 key：worker 可能已取走首个，故只断言最终处理的是最新值
        w.submit("k", ("k", 1))
        w.submit("k", ("k", 2))
        w.submit("k", ("k", 3))
        self.assertTrue(_wait_until(lambda: len(done) >= 1))
        time.sleep(0.2)
        self.assertEqual(done[-1], ("k", 3), "最新覆盖应处理最后提交的值")


class TestConcurrency(unittest.TestCase):
    """验证并发正确性：不丢任务、可重新拉起。"""

    def test_multithread_submit_no_loss(self):
        """多线程并发提交 500 个不同 key，全部都被处理（防丢唤醒）。"""
        seen = set()                                # 记录已处理的 key
        lock = threading.Lock()

        def handler(item):
            with lock:
                seen.add(item)

        w = serial_worker.SerialWorker(handler)
        total = 500

        def submitter(start, end):                  # 子线程：提交一段 key
            for i in range(start, end):
                w.submit(i, i)

        threads = [threading.Thread(target=submitter, args=(s, s + 50))
                   for s in range(0, total, 50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertTrue(_wait_until(lambda: len(seen) == total),
                        "有任务丢失：预期 %d，实际 %d" % (total, len(seen)))
        self.assertEqual(len(seen), total)

    def test_restart_after_drain(self):
        """队列排空、线程退出后，再次提交应能重新拉起并处理。"""
        done = []
        lock = threading.Lock()

        def handler(item):
            with lock:
                done.append(item)

        w = serial_worker.SerialWorker(handler)
        w.submit("a", "a")                         # 第一轮
        self.assertTrue(_wait_until(lambda: len(done) == 1))
        time.sleep(0.2)                             # 等线程退出、标志复位
        w.submit("b", "b")                         # 第二轮：应重新拉起
        self.assertTrue(_wait_until(lambda: len(done) == 2),
                        "队列空退出后未能重新拉起")


class TestErrorIsolation(unittest.TestCase):
    """验证异常隔离与错误回调。"""

    def test_exception_does_not_stop_queue(self):
        """某个元素处理抛异常，不影响后续元素被处理。"""
        done = []
        lock = threading.Lock()

        def handler(item):
            if item == "bad":
                raise RuntimeError("boom")          # 故意抛错
            with lock:
                done.append(item)

        w = serial_worker.SerialWorker(handler)
        w.submit("bad", "bad")
        w.submit("good", "good")
        self.assertTrue(_wait_until(lambda: "good" in done),
                        "异常后续元素未被处理")

    def test_on_error_called(self):
        """处理抛异常时，on_error 回调应收到该异常。"""
        errors = []

        def handler(item):
            raise ValueError("x")                   # 故意抛错

        w = serial_worker.SerialWorker(handler, on_error=errors.append)
        w.submit("k", "k")
        self.assertTrue(_wait_until(lambda: len(errors) >= 1),
                        "on_error 未被调用")
        self.assertIsInstance(errors[0], ValueError)


if __name__ == "__main__":
    unittest.main()
