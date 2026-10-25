"""read_file 正文投递方式开关：测试。

覆盖两种投递模式下的返回结构：
    开启（默认）——正文走附件引用，结果里出现 data.file 或 data.files；
    关闭       ——正文直接随结果返回，结果里出现 content 字段。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_read_file_delivery -v
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发 core/ 与 tools/ 的路径引导
import runtime
import file_read_impl


class TestReadFileDelivery(unittest.TestCase):
    """验证 read_file 在两种投递方式下的结果结构。"""

    def setUp(self):
        """建临时目录与样本文件，并保存原始配置以便还原。"""
        self.tmp = tempfile.mkdtemp(prefix="read_delivery_")
        self.sample = os.path.join(self.tmp, "sample.txt")
        with open(self.sample, "w", encoding="utf-8") as fh:
            fh.write("第一行\n第二行\n第三行\n")
        self._orig_config = runtime.CONFIG
        runtime.CONFIG = dict(self._orig_config or {})

    def tearDown(self):
        """还原配置并清理临时目录。"""
        runtime.CONFIG = self._orig_config
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _set_paste(self, enabled):
        """设置粘贴投递开关的当前值。"""
        runtime.CONFIG.setdefault("tool_config", {}).setdefault("read_file", {})[
            "paste_delivery"] = enabled

    def test_whole_file_paste_on_returns_attachment(self):
        """开启粘贴时，整文件读取返回附件引用而非正文。"""
        self._set_paste(True)
        r = file_read_impl.t_read_file({"file_path": self.sample})
        self.assertIn("data", r)
        self.assertIn("file", r["data"])
        self.assertNotIn("content", r)

    def test_whole_file_paste_off_returns_content(self):
        """关闭粘贴时，整文件读取直接返回正文。"""
        self._set_paste(False)
        r = file_read_impl.t_read_file({"file_path": self.sample})
        self.assertIn("content", r)
        self.assertIn("第二行", r["content"])
        self.assertNotIn("data", r)

    def test_segment_paste_off_returns_segment(self):
        """关闭粘贴时，分段读取返回所读行范围的内容。"""
        self._set_paste(False)
        r = file_read_impl.t_read_file(
            {"file_path": self.sample, "offset": 2, "limit": 1})
        self.assertIn("content", r)
        self.assertEqual(r["content"].strip(), "第二行")
        self.assertEqual(r["lines"], [2, 2])

    def test_batch_paste_off_returns_contents(self):
        """关闭粘贴时，批量读取的每个文件条目都带正文。"""
        self._set_paste(False)
        r = file_read_impl.t_read_file({"file_paths": [self.sample]})
        files = r["data"]["files"]
        self.assertEqual(len(files), 1)
        self.assertIn("content", files[0])

    def test_paste_switch_defaults_to_on(self):
        """配置缺省时按开启处理，保持附件投递的既有行为。"""
        runtime.CONFIG = {}
        self.assertTrue(file_read_impl._paste_enabled())


if __name__ == "__main__":
    unittest.main()
