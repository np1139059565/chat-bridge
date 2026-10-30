"""被动回复窗口持久化：测试。

覆盖四件事：
    1) 窗口与序号能跨「重启」原样恢复；
    2) 过期窗口载入时被丢弃；
    3) 文件缺失或损坏时安全退化为空表；
    4) 同一用户换新 msg_id 时旧窗口被覆盖。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_window_store -v
"""
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发 core/ 与 tools/ 的路径引导
from remote_bridge import window_store


class TestWindowStore(unittest.TestCase):
    """窗口存取的核心约定。"""

    def setUp(self):
        """把存盘路径指向临时目录，避免污染真实数据。"""
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = paths.BRIDGE_WINDOWS_PATH
        paths.BRIDGE_WINDOWS_PATH = os.path.join(self._tmp.name, "win.json")

    def tearDown(self):
        """还原路径并清理临时目录。"""
        paths.BRIDGE_WINDOWS_PATH = self._orig
        self._tmp.cleanup()

    def test_roundtrip_keeps_seq(self):
        """序号必须与窗口一起存取：只存 msg_id 会导致重数撞号。"""
        expire = time.time() + 600
        window_store.save({"u1": {"msg_id": "m1", "seq": 7, "expire": expire}})
        got = window_store.load()
        self.assertEqual(got["u1"]["msg_id"], "m1")
        self.assertEqual(got["u1"]["seq"], 7)
        self.assertAlmostEqual(got["u1"]["expire"], expire, places=2)

    def test_expired_window_dropped(self):
        """已过期的窗口不得恢复：QQ 侧已不接受该 msg_id。"""
        window_store.save({
            "old": {"msg_id": "m0", "seq": 3, "expire": time.time() - 10},
            "live": {"msg_id": "m1", "seq": 1, "expire": time.time() + 600},
        })
        got = window_store.load()
        self.assertNotIn("old", got)
        self.assertIn("live", got)

    def test_missing_file_returns_empty(self):
        """文件不存在时返回空表，不抛异常。"""
        self.assertEqual(window_store.load(), {})

    def test_corrupt_file_returns_empty(self):
        """文件损坏时返回空表：不能让服务起不来。"""
        with open(paths.BRIDGE_WINDOWS_PATH, "w", encoding="utf-8") as f:
            f.write("{ 这不是合法 json")
        self.assertEqual(window_store.load(), {})

    def test_newer_msg_id_overwrites(self):
        """同一用户换新 msg_id 时，旧窗口被覆盖（一人只留最近一个）。"""
        window_store.save({"u1": {"msg_id": "m1", "seq": 5, "expire": time.time() + 600}})
        window_store.save({"u1": {"msg_id": "m2", "seq": 0, "expire": time.time() + 600}})
        got = window_store.load()
        self.assertEqual(got["u1"]["msg_id"], "m2")
        self.assertEqual(got["u1"]["seq"], 0)

    def test_save_windows_snapshots_without_mutation(self):
        """save_windows 不应因写盘而改动传入的表。"""
        src = {"u1": {"msg_id": "m1", "seq": 2, "expire": time.time() + 600}}
        window_store.save_windows(src)
        self.assertEqual(src["u1"]["seq"], 2)
        self.assertEqual(window_store.load()["u1"]["seq"], 2)
