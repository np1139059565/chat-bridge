"""网页音频回收：上限裁剪与边界处理的测试。

背景：
    网页音频目录（data/web/audio）此前无任何自动清理，文件只增不减。
    web_mirror.prune_audio_files 在每次合成后按修改时间保留最近若干条，
    删除更旧的。本文件验证其裁剪行为与边界安全。

隔离策略：
    运行时替换 paths.WEB_AUDIO_DIR 到临时目录，只操作临时文件，不碰真实音频。

验证目标：
    1. 未超上限时一个都不删；
    2. 超上限时删到只剩 max_keep 个；
    3. 保留的是「最新」的那批（按修改时间）；
    4. 目录不存在时返回 0，不抛异常；
    5. 只统计普通文件，忽略子目录。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_audio_prune -v
"""
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import web_bridge.web_mirror as web_mirror


def _touch(d, name, mtime):
    """在目录 d 下建一个文件并设定修改时间。"""
    p = os.path.join(d, name)
    with open(p, "wb") as f:
        f.write(b"x")
    os.utime(p, (mtime, mtime))
    return p


class _Base(unittest.TestCase):
    """音频目录重定向到临时目录。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="audioprune_test_")
        self._orig = paths.WEB_AUDIO_DIR
        paths.WEB_AUDIO_DIR = Path(self.tmp) / "audio"
        os.makedirs(str(paths.WEB_AUDIO_DIR), exist_ok=True)

    def tearDown(self):
        paths.WEB_AUDIO_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestPruneAudio(_Base):
    """音频裁剪。"""

    def test_under_limit_deletes_nothing(self):
        """未超上限时不删任何文件。"""
        d = str(paths.WEB_AUDIO_DIR)
        for i in range(5):
            _touch(d, "out_%d.mp3" % i, time.time() + i)
        self.assertEqual(web_mirror.prune_audio_files(max_keep=10), 0)
        self.assertEqual(len(os.listdir(d)), 5)

    def test_over_limit_trims_to_keep(self):
        """超上限时删到只剩 max_keep 个。"""
        d = str(paths.WEB_AUDIO_DIR)
        for i in range(20):
            _touch(d, "out_%d.mp3" % i, time.time() + i)
        removed = web_mirror.prune_audio_files(max_keep=8)
        self.assertEqual(removed, 12)
        self.assertEqual(len(os.listdir(d)), 8)

    def test_keeps_newest_files(self):
        """保留的应是修改时间最新的那批。"""
        d = str(paths.WEB_AUDIO_DIR)
        base = time.time()
        # 建 5 个文件，时间递增：old_0 最旧，old_4 最新
        for i in range(5):
            _touch(d, "old_%d.mp3" % i, base + i)
        web_mirror.prune_audio_files(max_keep=2)
        left = sorted(os.listdir(d))
        self.assertEqual(left, ["old_3.mp3", "old_4.mp3"])

    def test_missing_dir_returns_zero(self):
        """目录不存在时返回 0，不抛异常。"""
        paths.WEB_AUDIO_DIR = Path(self.tmp) / "nope"
        self.assertEqual(web_mirror.prune_audio_files(), 0)

    def test_ignores_subdirectories(self):
        """子目录不应被当作文件统计或删除。"""
        d = str(paths.WEB_AUDIO_DIR)
        for i in range(3):
            _touch(d, "out_%d.mp3" % i, time.time() + i)
        os.makedirs(os.path.join(d, "subdir"), exist_ok=True)
        # 3 个文件未超上限 10，子目录不算文件，故不删
        self.assertEqual(web_mirror.prune_audio_files(max_keep=10), 0)
        self.assertTrue(os.path.isdir(os.path.join(d, "subdir")))

    def test_default_limit_matches_retention(self):
        """默认上限应与统一保留口径一致（消息与音频同源）。"""
        from app_limits import MAX_AUDIO_FILES, MAX_MESSAGES
        self.assertEqual(web_mirror.MAX_AUDIO_FILES, MAX_AUDIO_FILES)
        # 音频与消息同口径：消息还在时，其引用的音频一定还在
        self.assertEqual(MAX_AUDIO_FILES, MAX_MESSAGES)


if __name__ == "__main__":
    unittest.main()
