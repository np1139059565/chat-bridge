"""read_file 空内容处理测试

覆盖点：正文为空时不得产出可粘贴附件。

为何要测：前端只在结果里出现 data.file / data.files 时才触发粘贴；
若空内容也带附件字段，前端会去粘贴一个空文件，取不到文字即报
「未提取到文字」，使 AI 无法继续执行。故此处把「空内容不产附件」
作为对外契约固定下来。
"""
import os
import shutil
import sys
import tempfile
import unittest


# 保证能导入 tools 包与 core 下的顶层模块（screenshot_store 等）
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_BASE, os.path.join(_BASE, "core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools import file_read_impl as fr  # noqa: E402


class ReadFileEmptyTestCase(unittest.TestCase):
    """空内容与正常内容的读取结果差异。"""

    def setUp(self):
        """建临时目录，准备一个空文件与一个正常文件。"""
        self.tmp = tempfile.mkdtemp(prefix="readempty_test_")
        self.empty = os.path.join(self.tmp, "empty.txt")
        open(self.empty, "w", encoding="utf-8").close()
        self.normal = os.path.join(self.tmp, "normal.txt")
        with open(self.normal, "w", encoding="utf-8") as fh:
            fh.write("第一行\n第二行\n第三行\n")

    def tearDown(self):
        """清理临时目录。"""
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _has_attachment(result):
        """判断结果里是否带可粘贴附件（前端据此触发粘贴）。"""
        data = (result or {}).get("data") or {}
        return bool(data.get("file") or data.get("files"))

    def test_empty_segment_has_no_attachment(self):
        """空文件分段读取：不产出附件，并标记为空。"""
        r = fr.t_read_file({"path": self.empty, "offset": 1, "limit": 10})
        self.assertFalse(self._has_attachment(r))
        self.assertTrue(r.get("empty"))
        self.assertIn("为空", r.get("message") or "")

    def test_empty_whole_has_no_attachment(self):
        """空文件整文件读取：不产出附件，并标记为空。"""
        r = fr.t_read_file({"path": self.empty})
        self.assertFalse(self._has_attachment(r))
        self.assertTrue(r.get("empty"))

    def test_offset_past_end_has_no_attachment(self):
        """起始行越过文件末尾：不产出附件。"""
        r = fr.t_read_file({"path": self.normal, "offset": 9999, "limit": 5})
        self.assertFalse(self._has_attachment(r))
        self.assertTrue(r.get("empty"))

    def test_batch_whole_skips_empty_file(self):
        """批量整读：空文件被跳过，正常文件仍给附件。"""
        r = fr.t_read_file({"path": [self.empty, self.normal]})
        data = r.get("data") or {}
        files = data.get("files") or []
        self.assertEqual(len(files), 1)
        self.assertEqual(os.path.basename(files[0]["path"]), "normal.txt")
        # 比对文件名而非完整路径：Windows 可能返回 8.3 短路径（形如 ADMINI~1），
        # 与传参时的长路径字符串不同，但指向同一文件。
        empties = r.get("empty_files") or []
        self.assertEqual([os.path.basename(p) for p in empties], ["empty.txt"])

    def test_batch_segment_all_empty_has_no_attachment(self):
        """批量分段且全为空：不产出附件。

        回归点：read_lines 按「请求行数」计算，空文件也会被算成读了 N 行，
        故不能用行数判空，必须看是否真的读到正文。
        """
        r = fr.t_read_file({"path": [self.empty], "offset": 1, "limit": 5})
        self.assertFalse(self._has_attachment(r))
        self.assertTrue(r.get("empty"))

    def test_normal_segment_still_has_attachment(self):
        """正常文件分段读取：照常产出附件，不被空内容逻辑误伤。"""
        r = fr.t_read_file({"path": self.normal, "offset": 1, "limit": 2})
        self.assertTrue(self._has_attachment(r))
        self.assertFalse(r.get("empty"))

    def test_normal_whole_still_has_attachment(self):
        """正常文件整读：照常产出源文件引用。"""
        r = fr.t_read_file({"path": self.normal})
        data = r.get("data") or {}
        self.assertTrue(data.get("file"))
        self.assertTrue(data["file"].get("source"))


if __name__ == "__main__":
    unittest.main()
