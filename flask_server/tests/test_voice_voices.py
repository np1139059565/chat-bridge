"""音色清单测试（voice_voices 执行路径）

背景：
  该模块此前零覆盖。它负责按引擎列出可选音色，供设置页下拉选择。
  音色列举错了，用户选到的名字与实际合成用的不一致，表现为
  「设置里选了某音色、播出来还是默认的」，且不会报错。

覆盖点：
  1. list_voices 的引擎路由：四种引擎各自走到对应的列举函数
  2. 未指定引擎时按 fallback 首个引擎列举
  3. 各引擎的 current 取值来源不同，逐一对上
  4. edge_tts 内置清单非空且字段完整
  5. 列举失败时返回空列表，不抛异常

运行：python -m pytest tests/test_voice_voices.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import voice_voices as vv


class ListVoicesRoutingTest(unittest.TestCase):
    """引擎路由：选对列举函数与 current 来源。"""

    def setUp(self):
        """保存原始函数，便于逐用例替换与还原。"""
        self._orig = {
            "cfg": vv._load_voice_cfg,
            "order": vv._engine_order,
            "pyttsx3": vv._list_pyttsx3_voices,
            "piper": vv._list_piper_voices,
            "sapi": vv._list_sapi_voices,
            "edge": vv._list_edge_voices,
        }

    def tearDown(self):
        """还原全部被替换的函数。"""
        vv._load_voice_cfg = self._orig["cfg"]
        vv._engine_order = self._orig["order"]
        vv._list_pyttsx3_voices = self._orig["pyttsx3"]
        vv._list_piper_voices = self._orig["piper"]
        vv._list_sapi_voices = self._orig["sapi"]
        vv._list_edge_voices = self._orig["edge"]

    def _stub_all(self, cfg=None):
        """把所有列举函数替换成固定返回值，便于观察路由。

        @param cfg 配置字典
        """
        vv._load_voice_cfg = lambda: (cfg or {})
        vv._engine_order = lambda c: ["pyttsx3"]
        vv._list_pyttsx3_voices = lambda: [{"id": "p1", "name": "P1"}]
        vv._list_piper_voices = lambda: [{"id": "m.onnx", "name": "m"}]
        vv._list_sapi_voices = lambda: [{"id": "s1", "name": "S1"}]
        vv._list_edge_voices = lambda: [{"id": "e1", "name": "E1"}]

    def test_pyttsx3_engine(self):
        """pyttsx3：走系统音色列举，current 取 pyttsx3_voice。"""
        self._stub_all({"pyttsx3_voice": " 选中的 "})
        out = vv.list_voices("pyttsx3")
        self.assertEqual(out["engine"], "pyttsx3")
        self.assertEqual(out["voices"][0]["id"], "p1")
        # current 去掉首尾空白
        self.assertEqual(out["current"], "选中的")

    def test_piper_engine(self):
        """piper：走模型文件列举，current 取 piper_model。"""
        self._stub_all({"piper_model": "/models/a.onnx"})
        out = vv.list_voices("piper")
        self.assertEqual(out["engine"], "piper")
        self.assertEqual(out["voices"][0]["name"], "m")
        self.assertEqual(out["current"], "/models/a.onnx")

    def test_sapi_engine(self):
        """sapi：走 PowerShell 列举，current 取 sapi_voice。"""
        self._stub_all({"sapi_voice": "S1"})
        out = vv.list_voices("sapi")
        self.assertEqual(out["engine"], "sapi")
        self.assertEqual(out["current"], "S1")

    def test_edge_engine(self):
        """edge_tts：走内置清单，current 固定为默认音色。"""
        self._stub_all()
        out = vv.list_voices("edge_tts")
        self.assertEqual(out["engine"], "edge_tts")
        self.assertEqual(out["current"], vv.DEFAULT_VOICE)

    def test_engine_name_case_insensitive(self):
        """引擎名大小写不敏感，前后空白被去掉。"""
        self._stub_all()
        out = vv.list_voices("  Piper  ")
        self.assertEqual(out["engine"], "piper")

    def test_unknown_engine_yields_empty(self):
        """未知引擎：返回空列表而非报错。"""
        self._stub_all()
        out = vv.list_voices("nosuch")
        self.assertEqual(out["voices"], [])
        self.assertEqual(out["current"], "")

    def test_auto_uses_first_of_fallback(self):
        """未指定引擎时，按 fallback 首个引擎列举。"""
        vv._load_voice_cfg = lambda: {}
        vv._engine_order = lambda c: ["edge_tts", "pyttsx3"]
        vv._list_edge_voices = lambda: [{"id": "e1", "name": "E1"}]
        out = vv.list_voices()
        self.assertEqual(out["engine"], "edge_tts")

    def test_auto_falls_back_to_pyttsx3_when_order_empty(self):
        """fallback 为空时退化为 pyttsx3。"""
        vv._load_voice_cfg = lambda: {}
        vv._engine_order = lambda c: []
        vv._list_pyttsx3_voices = lambda: [{"id": "p1", "name": "P1"}]
        out = vv.list_voices()
        self.assertEqual(out["engine"], "pyttsx3")


class EdgeVoicesTest(unittest.TestCase):
    """edge_tts 内置清单：不依赖外部环境，可直接断言。"""

    def test_returns_non_empty(self):
        """清单非空。"""
        self.assertTrue(len(vv._list_edge_voices()) > 0)

    def test_each_item_has_id_and_name(self):
        """每项都有 id 与 name，且都非空——缺 id 会让合成拿不到音色名。"""
        for v in vv._list_edge_voices():
            self.assertTrue(v.get("id"))
            self.assertTrue(v.get("name"))

    def test_default_voice_in_list(self):
        """默认音色必须在清单里，否则界面显示与实际不一致。"""
        ids = [v["id"] for v in vv._list_edge_voices()]
        self.assertIn(vv.DEFAULT_VOICE, ids)


if __name__ == "__main__":
    unittest.main()
