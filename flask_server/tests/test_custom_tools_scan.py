"""技能目录扫描：扫描结果不包含已安装条目。

运行方式（在 flask_server/ 目录下）：
    python -m unittest discover -s tests -p test_custom_tools_scan.py -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# 让 import paths / custom_tools 命中 flask_server 根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import custom_tools.scan as scan_mod


def _write_skill(root, name, tool_names, with_doc=False):
    """在临时根目录造一个 skill；tool_names 为 None 表示只有说明文档。"""
    d = Path(root) / name
    d.mkdir(parents=True, exist_ok=True)
    if with_doc:
        (d / "SKILL.md").write_text("# " + name, encoding="utf-8")
    if tool_names is None:
        return str(d)
    tools = [{
        "name": n, "description": "工具 " + n,
        "script": "scripts/run.py", "interpreter": "python", "parameters": [],
    } for n in tool_names]
    (d / "scripts").mkdir(exist_ok=True)
    (d / "scripts" / "run.py").write_text("print(1)", encoding="utf-8")
    (d / "tool.json").write_text(json.dumps({"tools": tools}, ensure_ascii=False), encoding="utf-8")
    return str(d)


class TestScanDirFiltersInstalled(unittest.TestCase):
    """已安装工具不进扫描结果；工具全装完的 skill 整条略过。"""

    def setUp(self):
        # 临时目录隔离，不触碰工程内真实 skills 与配置
        self.tmp = tempfile.mkdtemp(prefix="ctscan_test_")
        self.root = os.path.join(self.tmp, "skills")
        os.makedirs(self.root)
        _write_skill(self.root, "part", ["t_installed", "t_new"])
        _write_skill(self.root, "all", ["t_done"])
        _write_skill(self.root, "fresh", ["t_fresh"])
        _write_skill(self.root, "doconly", None, with_doc=True)
        bad = Path(self.root) / "broken"
        bad.mkdir()
        (bad / "tool.json").write_text("{ not json", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _scan(self, installed_names):
        """用替身注册表替换 load_tools，避免读写真实配置文件。"""
        fake = {n: {"name": n} for n in installed_names}
        with mock.patch.object(scan_mod, "load_tools", return_value=fake):
            return scan_mod.scan_dir(self.root)

    def test_filters_installed_tools_and_full_installed_skill(self):
        """部分安装的 skill 只留未安装工具；全部安装的整条不返回。"""
        res = self._scan(["t_installed", "t_done"])
        by_name = {s["skill_name"]: s for s in res}
        self.assertNotIn("all", by_name)
        self.assertEqual([t["name"] for t in by_name["part"]["tools"]], ["t_new"])
        self.assertEqual([t["name"] for t in by_name["fresh"]["tools"]], ["t_fresh"])
        # 说明文档型空技能没有可安装条目，照常保留
        self.assertIn("doconly", by_name)
        self.assertEqual(by_name["doconly"]["tools"], [])
        # 解析失败条目保留，便于用户看到原因
        self.assertIn("error", by_name["broken"])
        # 返回的工具一律不是已安装态
        for s in res:
            for t in s["tools"]:
                self.assertFalse(t.get("installed", False))

    def test_no_installed_tools_returns_all_skills(self):
        """无已安装工具时，所有 skill 都在扫描结果里。"""
        res = self._scan([])
        names = sorted(s["skill_name"] for s in res)
        self.assertEqual(names, ["all", "broken", "doconly", "fresh", "part"])


if __name__ == "__main__":
    unittest.main()
