"""元宝站点不接收 paste 图片：档案应显式关闭 filePaste，走结果直返。

回归：read_image 在 yuanbao.tencent.com 只回存档路径、图进不了输入框
（2026-11-12 P5）。真源 config/definition.yaml 原先无 filePaste，
_site_allows_paste 缺省 True 走粘贴链路。
导入方式与 test_file_paste_mode.py 一致（扁平模块 + core/tools 入 sys.path）。
"""
import os
import sys
import unittest

_ROOT = os.path.join(os.path.dirname(__file__), "..")
for _p in (_ROOT, os.path.join(_ROOT, "core"), os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import file_delivery  # noqa: E402
import runtime  # noqa: E402

DEF = os.path.join(_ROOT, "config", "definition.yaml")


def _yuanbao_lines():
    with open(DEF, encoding="utf-8") as f:
        lines = f.read().splitlines()
    start = next(i for i, l in enumerate(lines)
                 if l.startswith("    yuanbao:"))
    end = len(lines)
    for i in range(start + 1, len(lines)):
        l = lines[i]
        lead = len(l) - len(l.lstrip(" "))
        if l.strip() and lead <= 4:
            end = i
            break
    return lines[start:end]


class TestYuanbaoFilePaste(unittest.TestCase):
    def setUp(self):
        self._cfg = dict(runtime.CONFIG)

    def tearDown(self):
        runtime.CONFIG.clear()
        runtime.CONFIG.update(self._cfg)

    def test_profile_disables_file_paste(self):
        rows = [l.strip() for l in _yuanbao_lines()
                if l.strip().startswith("filePaste:")]
        self.assertEqual(rows, ["filePaste: false"])

    def test_yuanbao_url_does_not_paste(self):
        runtime.CONFIG.clear()
        runtime.CONFIG.update({
            "site_profiles": {"yuanbao.tencent.com": "yuanbao"},
            "profiles": {"yuanbao": {"filePaste": False}},
        })
        self.assertIs(file_delivery._site_allows_paste(
            "https://yuanbao.tencent.com/chat/naRmT"), False)

    def test_other_site_still_allows_paste(self):
        runtime.CONFIG.clear()
        runtime.CONFIG.update({
            "site_profiles": {"deepseek.com": "deepseek"},
            "profiles": {"deepseek": {}},
        })
        self.assertIs(file_delivery._site_allows_paste(
            "https://deepseek.com/chat/x"), True)


if __name__ == "__main__":
    unittest.main(verbosity=2)