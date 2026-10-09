"""截图与网页图片存盘：格式推断、文件名唯一性、失败兜底的测试。

背景：
    screenshot_store 统一了此前两份重复的 dataURL 存盘实现，负责 QQ 截图与
    网页结果图片的落盘。此前无任何测试。

隔离策略：
    运行时替换 paths.SCREENSHOTS_DIR / paths.WEB_IMAGES_DIR 到临时目录，
    使存盘落在临时目录，结束后复原。

验证目标：
    1. save_data_url：PNG / JPEG 扩展名推断正确、返回 {name, path} 且文件存在；
    2. 非法输入（空、无逗号）返回 None，不抛异常；
    3. 连续两次保存文件名不同（序号防撞名）；
    4. save_web_image：落在网页图片目录，前缀为 web_。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_screenshot_store -v
"""
import base64
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import screenshot_store

# 1x1 透明 PNG 的 base64
_PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
            "YAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


def _png_data_url():
    """构造一个合法的 PNG dataURL。"""
    return "data:image/png;base64," + _PNG_B64


def _jpeg_data_url():
    """构造一个 JPEG dataURL（内容非真 JPEG，但仅用于验证扩展名推断）。"""
    return "data:image/jpeg;base64," + _PNG_B64


class _Base(unittest.TestCase):
    """截图目录与网页图片目录重定向到临时目录。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="shot_test_")
        self._orig_shot = paths.SCREENSHOTS_DIR
        self._orig_web = paths.WEB_IMAGES_DIR
        paths.SCREENSHOTS_DIR = Path(self.tmp) / "shots"
        paths.WEB_IMAGES_DIR = Path(self.tmp) / "webimages"

    def tearDown(self):
        paths.SCREENSHOTS_DIR = self._orig_shot
        paths.WEB_IMAGES_DIR = self._orig_web
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestSaveDataUrl(_Base):
    """QQ 截图存盘。"""

    def test_png_extension(self):
        """PNG dataURL 应存成 .png 且文件存在。"""
        res = screenshot_store.save_data_url(_png_data_url())
        self.assertIsNotNone(res)
        self.assertTrue(res["name"].endswith(".png"))
        self.assertTrue(os.path.exists(res["path"]))

    def test_jpeg_extension(self):
        """JPEG dataURL 应存成 .jpg。"""
        res = screenshot_store.save_data_url(_jpeg_data_url())
        self.assertTrue(res["name"].endswith(".jpg"))

    def test_content_written(self):
        """落盘内容应与解码后的原始字节一致。"""
        res = screenshot_store.save_data_url(_png_data_url())
        with open(res["path"], "rb") as f:
            self.assertEqual(f.read(), base64.b64decode(_PNG_B64))

    def test_unique_names_on_rapid_calls(self):
        """连续两次保存文件名应不同（序号防撞名）。"""
        r1 = screenshot_store.save_data_url(_png_data_url())
        r2 = screenshot_store.save_data_url(_png_data_url())
        self.assertNotEqual(r1["name"], r2["name"])

    def test_empty_returns_none(self):
        """空输入返回 None。"""
        self.assertIsNone(screenshot_store.save_data_url(""))
        self.assertIsNone(screenshot_store.save_data_url(None))

    def test_no_comma_returns_none(self):
        """无逗号的非法 dataURL 返回 None，不抛异常。"""
        self.assertIsNone(screenshot_store.save_data_url("data:image/png;base64"))


class TestSaveWebImage(_Base):
    """网页结果图片存盘。"""

    def test_prefix_and_dir(self):
        """文件名应以 web_ 开头，且落在网页图片目录。"""
        res = screenshot_store.save_web_image(_png_data_url())
        self.assertIsNotNone(res)
        self.assertTrue(res["name"].startswith("web_"))
        self.assertIn("webimages", res["path"])
        self.assertTrue(os.path.exists(res["path"]))

    def test_invalid_returns_none(self):
        """非法输入返回 None。"""
        self.assertIsNone(screenshot_store.save_web_image("bad"))


if __name__ == "__main__":
    unittest.main()
