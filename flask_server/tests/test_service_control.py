"""服务进程控制：日志路径、端口探测、重启分支的测试。

背景：
    service_control 负责同端口重启与滚动重启，会真正启动子进程与退出进程。
    此前无任何测试。

安全策略（关键）：
    本测试**不真正拉起或退出任何进程**。全部用替身拦截：
    - 拦截 subprocess.Popen，避免真的启动服务；
    - 拦截 os._exit，避免测试进程退出；
    - 拦截 threading.Timer / Thread 的启动，避免后台动作；
    - 拦截 urllib.request.urlopen，避免真实网络请求。

验证目标：
    1. _log_path：按天分文件，路径落在 data/logs 下、含当天日期；
    2. _port_alive：urlopen 正常返回 200 判真，异常判假；
    3. restart_server：调用 _spawn 并安排了退出定时器；
    4. rolling_restart：立即返回并起了后台线程（不阻塞调用方）。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_service_control -v
"""
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import service_control


class TestLogPath(unittest.TestCase):
    """重启日志路径。"""

    def test_log_path_shape(self):
        """应落在 data/logs 下、按天分文件。"""
        p = service_control._log_path()
        self.assertIn(os.path.join("data", "logs"), p)
        self.assertTrue(os.path.basename(p).startswith("restart-"))
        self.assertIn(time.strftime("%Y-%m-%d"), p)


class TestPortAlive(unittest.TestCase):
    """端口探测。"""

    def test_returns_true_on_200(self):
        """urlopen 返回 200 时判真。"""
        resp = mock.MagicMock()
        resp.status = 200
        with mock.patch.object(service_control.urllib.request, "urlopen", return_value=resp):
            self.assertTrue(service_control._port_alive(5000))

    def test_returns_false_on_exception(self):
        """请求抛异常时判假。"""
        with mock.patch.object(service_control.urllib.request, "urlopen",
                               side_effect=OSError("refused")):
            self.assertFalse(service_control._port_alive(5000))


class TestSpawn(unittest.TestCase):
    """子进程启动（用替身拦截，不真正启动）。"""

    def test_spawn_calls_popen(self):
        """_spawn 应调用 subprocess.Popen（被替身拦截）。"""
        with mock.patch.object(service_control.subprocess, "Popen") as popen, \
             mock.patch.object(service_control, "_log_path", return_value=os.devnull):
            service_control._spawn(extra_args=["--port", "5006"])
        self.assertTrue(popen.called)

    def test_spawn_with_delay_uses_bootstrap(self):
        """带延迟时应走引导代码分支（popen 命令含 -c）。"""
        with mock.patch.object(service_control.subprocess, "Popen") as popen, \
             mock.patch.object(service_control, "_log_path", return_value=os.devnull):
            service_control._spawn(delay=1.0)
        args = popen.call_args[0][0]
        self.assertIn("-c", args)


class TestRestartServer(unittest.TestCase):
    """同端口重启。"""

    def test_restart_spawns_and_schedules_exit(self):
        """应调用 _spawn 并安排退出定时器（均用替身拦截，不产生真实动作）。"""
        with mock.patch.object(service_control, "_spawn") as spawn, \
             mock.patch.object(service_control.threading, "Timer") as timer:
            service_control.restart_server()
        self.assertTrue(spawn.called)
        self.assertTrue(timer.called)


class TestRollingRestart(unittest.TestCase):
    """滚动重启。"""

    def test_returns_immediately(self):
        """应立即返回（后台线程完成，不阻塞调用方）。"""
        started = {}

        class _FakeThread:
            def __init__(self, target=None, daemon=None, **kw):
                started["target"] = target

            def start(self):
                started["started"] = True

        with mock.patch.object(service_control.threading, "Thread", _FakeThread):
            t0 = time.time()
            service_control.rolling_restart(5007, timeout=0.1)
            elapsed = time.time() - t0
        self.assertLess(elapsed, 0.5)          # 未被后台等待阻塞
        self.assertTrue(started.get("started"))


if __name__ == "__main__":
    unittest.main()
