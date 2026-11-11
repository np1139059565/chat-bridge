"""C-3b：站点档案真源切换到客户端注册信息后的端到端验收。

覆盖：
  1. 含中文 / 嵌套 / null 的整份站点档案，存一遍取一遍逐字段一致；
  2. 按 site_key 隔离，两个客户端互不串；
  3. 未注册不兜底（/api/clients 404、/profiles 不含默认档案）；
  4. POST /config 的 profiles 区块与寄存通道互通，重复注册整条覆盖。

隔离：REGISTRY_PATH 重定向到临时文件，不触碰真实注册数据。
"""
import copy
import unittest
from pathlib import Path

from flask import Flask, request

import runtime
import client_registry as registry
from routes import config_route
from routes.clients import bp as clients_bp


def _preflight():
    """OPTIONS 预检统一返回 204。"""
    if request.method == "OPTIONS":
        return ("", 204)


def _build_app():
    app = Flask("site_profiles_test")
    app.register_blueprint(config_route.bp)
    app.register_blueprint(clients_bp)
    app.before_request(_preflight)
    return app


class SiteProfileRegistryTest(unittest.TestCase):
    """站点档案寄存通道的六项验收。"""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="siteprof_test_")
        self._orig_path = registry.REGISTRY_PATH
        self._orig_config = copy.deepcopy(runtime.CONFIG)
        registry.REGISTRY_PATH = Path(self.tmp) / "client_registry.json"
        self.app = _build_app()
        self.client = self.app.test_client()
        # 写其它配置区块不应落盘（与 test_config_route 同口径）
        config_route.save_config_to_yaml = lambda: True

    def tearDown(self):
        registry.REGISTRY_PATH = self._orig_path
        runtime.CONFIG.clear()
        runtime.CONFIG.update(self._orig_config)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_deep_equal_chinese_nested_null(self):
        """整份站点档案含中文/嵌套/null/特殊字符，存一遍取一遍逐字段一致。"""
        profile = {
            "label": "智谱清言",
            "hosts": ["chatglm.cn", "chatglm.com"],
            "container": ".detail.chatScrollContainer",
            "中文键": {"嵌套": {"三": ["甲", 0, True, None], "备注": "引号\" 换行\n 反斜杠\\"}},
            "空值": None,
            "空字符串": "",
            "split": False,
        }
        r = self.client.post("/api/clients", json={
            "site_key": "glm", "custom_config": profile, "commands": []})
        self.assertEqual(r.status_code, 200)
        # 经 C-3a 通道取回，逐字段一致
        got = self.client.get("/api/clients?site_key=glm").get_json()["custom_config"]
        self.assertEqual(got, profile)
        # 经 C-3b 的 GET /profiles 聚合视图取回，同样逐字段一致
        agg = self.client.get("/profiles").get_json()["profiles"]
        self.assertEqual(agg["glm"], profile)
        # GET /config 界面快照同源
        self.assertEqual(self.client.get("/config").get_json()["profiles"]["glm"], profile)

    def test_site_key_isolation(self):
        """两个 site_key 的档案互不串。"""
        a = {"label": "甲", "hosts": ["a.example"], "独有": {"x": 1}}
        b = {"label": "乙", "hosts": ["b.example"], "独有": {"y": None}}
        self.client.post("/api/clients", json={"site_key": "glm", "custom_config": a, "commands": []})
        self.client.post("/api/clients", json={"site_key": "qianwen", "custom_config": b, "commands": []})
        profs = self.client.get("/profiles").get_json()["profiles"]
        self.assertEqual(set(profs), {"glm", "qianwen"})
        self.assertEqual(profs["glm"], a)
        self.assertEqual(profs["qianwen"], b)

    def test_unregistered_no_fallback(self):
        """未注册 site_key 返回 404 与明确错误；/profiles 不兜底默认档案。"""
        runtime.CONFIG["profiles"] = {"glm": {"label": "出厂GLM", "hosts": ["chatglm.cn"]}}
        r = self.client.get("/api/clients?site_key=qianwen")
        self.assertEqual(r.status_code, 404)
        self.assertIn("客户端未注册", r.get_json()["error"])
        self.assertEqual(self.client.get("/profiles").get_json()["profiles"], {})
        self.assertEqual(self.client.get("/config").get_json()["profiles"], {})

    def test_post_config_writes_registry(self):
        """设置页保存（POST /config）写入寄存通道，且原样不清洗。"""
        # 内存里放一份出厂种子（模拟 definition.yaml 读入），验证 POST 不改写它。
        runtime.CONFIG["profiles"] = {"glm": {"label": "出厂GLM"}}
        entry = {"label": "千问", "hosts": ["qianwen.com"],
                 "容器特征": {"生成态": ["aside.x", None], "重试": 3}, "备注": None}
        r = self.client.post("/config", json={"profiles": {"qianwen": entry}})
        self.assertEqual(r.status_code, 200)
        self.assertIn("profiles", r.get_json()["changed"])
        self.assertEqual(self.client.get("/api/clients?site_key=qianwen").get_json()["custom_config"], entry)
        # 真源不在 definition.yaml：内存出厂种子未被 POST 写入或改写。
        self.assertNotIn("qianwen", runtime.CONFIG["profiles"])
        self.assertEqual(runtime.CONFIG["profiles"]["glm"]["label"], "出厂GLM")

    def test_repeated_register_overwrites_whole_entry(self):
        """同一 site_key 重复寄存整条覆盖，不追加。"""
        self.client.post("/api/clients", json={
            "site_key": "glm", "custom_config": {"label": "旧", "多余": 1}, "commands": []})
        self.client.post("/api/clients", json={
            "site_key": "glm", "custom_config": {"label": "新"}, "commands": []})
        got = self.client.get("/api/clients?site_key=glm").get_json()["custom_config"]
        self.assertEqual(got, {"label": "新"})

    def test_profiles_remove_unregisters(self):
        """profiles_remove 显式注销，只删列出的 id。"""
        self.client.post("/config", json={"profiles": {
            "glm": {"label": "GLM"}, "kimi": {"label": "K"}}})
        self.client.post("/config", json={"profiles_remove": ["kimi"]})
        profs = self.client.get("/profiles").get_json()["profiles"]
        self.assertEqual(set(profs), {"glm"})


if __name__ == "__main__":
    unittest.main()
