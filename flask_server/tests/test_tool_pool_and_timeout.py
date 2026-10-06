"""工具线程池防护与超时关系：测试。

背景（走查发现）：
    1) 所有内置工具共用一个线程池。Python 无法强制终止运行中的线程，
       超时后该线程仍在后台跑、占着池里的坑。池子仅 16 个 worker，
       积累满即导致后续工具调用全部排队（前端表现为「卡死」）。
       修复目标：扩容到 64，且超时后重建线程池，让卡住的旧 worker
       随旧池被抛弃、新池使用全新 worker。
    2) 外层兜底超时 BUILTIN_TOOL_TIMEOUT（120s）必须大于脚本类工具
       自身超时 RUN_COMMAND_TIMEOUT（60s）。2-A 方案：两者一起下调，
       内层 60→45，外层 120→60，仍保持外层大于内层。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_tool_pool_and_timeout -v
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发 core/ 与 tools/ 的路径引导
import run_command_impl
from routes import tools as tools_route


class TestTimeoutValues(unittest.TestCase):
    """验证超时常量按 2-A 方案下调，且内外层关系正确。"""

    def test_run_command_timeout_is_45(self):
        """脚本类工具自身超时应为 45 秒（原 60）。"""
        self.assertEqual(run_command_impl.RUN_COMMAND_TIMEOUT, 45)

    def test_builtin_tool_timeout_is_60(self):
        """外层兜底超时应为 60 秒（原 120）。"""
        self.assertEqual(tools_route.BUILTIN_TOOL_TIMEOUT, 60)

    def test_outer_greater_than_inner(self):
        """外层必须严格大于内层，否则正常慢命令会被外层误杀。"""
        self.assertGreater(
            tools_route.BUILTIN_TOOL_TIMEOUT,
            run_command_impl.RUN_COMMAND_TIMEOUT,
        )


class TestToolPoolDefense(unittest.TestCase):
    """验证工具线程池的容量与超时后的重建行为。"""

    def test_pool_max_workers_is_64(self):
        """线程池容量应为 64（原 16），为卡住的线程留足余量。"""
        self.assertEqual(tools_route._TOOL_POOL._max_workers, 64)

    def test_timeout_triggers_pool_rebuild(self):
        """工具超时后应触发线程池重建：旧 worker 随旧池抛弃，新池用新 worker。

        做法：用一个必然超时的慢函数（睡 1 秒）配 0.1 秒超时，
        断言超时被抛出，且池的「代次」计数增加（说明发生了重建）。
        """
        gen_before = tools_route._pool_generation

        def _slow(params):
            time.sleep(1.0)
            return "done"

        with self.assertRaises(TimeoutError):
            tools_route._run_with_timeout(_slow, {}, 0.1)

        self.assertGreater(
            tools_route._pool_generation, gen_before,
            "超时后应重建线程池，代次计数未增加",
        )

    def test_rebuild_returns_usable_pool(self):
        """重建后的线程池仍可正常执行任务。"""
        pool = tools_route._rebuild_tool_pool()
        self.assertEqual(pool._max_workers, 64)
        # 新池能正常跑一个快任务
        fut = pool.submit(lambda: 42)
        self.assertEqual(fut.result(timeout=5), 42)


if __name__ == "__main__":
    unittest.main()
