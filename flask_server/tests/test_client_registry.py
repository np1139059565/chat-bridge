r"""客户端注册接口测试：覆盖注册 / 取回 / 注销与持久化。

隔离策略：
    不调用 create_app（会启动看门狗与后台线程），只注册被测蓝图；
    把 core/client_registry.py 的 REGISTRY_PATH 重定向到临时文件，
    测试不触碰 .\flask_server\data\ 下的真实注册数据。

运行方式（在 .\flask_server\ 目录下）：
    python -m pytest tests/test_client_registry.py -q
"""
import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# 把服务根加入搜索路径，使被测模块可直接导入。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from flask import Flask

import client_registry as registry
from routes.clients import bp as clients_bp


def _preflight():
    """OPTIONS 预检统一返回 204，避免进入视图函数。"""
    # 只在预检时短路，其余方法交给蓝图视图处理。
    from flask import request
    if request.method == "OPTIONS":
        return ("", 204)


def _build_app():
    """构造只注册客户端注册蓝图的最小应用。"""
    app = Flask("clients_test")
    app.register_blueprint(clients_bp)
    # 预检处理函数单独定义，保持应用装配逻辑简短。
    app.before_request(_preflight)
    return app


# 含中文、数组、嵌套对象、空字符串、null、特殊字符的配置，用于逐字节一致实测。
_RICH_CONFIG = {
    "语言包": {
        "输入框": "#search-input-box textarea",
        "容器": "[class*=message-list]",
        "嵌套": {"层级": {"三": ["甲", "乙", 3, True, None]}},
    },
    "别名": ["甲", "乙"],
    "空字符串": "",
    "空值": None,
    "特殊字符": "引号\" 单引号' 换行\n 制表\t 反斜杠\\ 中文😀 <>&",
    "数字": 0,
}

# 可执行指令声明：沿用 extensions.md 第四节的 commands 格式，本阶段仅登记。
_COMMANDS = [
    {"name": "/dbg-open", "alias": "/do", "desc": "打开调试抽屉", "tool": "open_drawer"},
]


class ClientRegistryTest(unittest.TestCase):
    """六个验收场景 + 重启后取回。"""

    def setUp(self):
        """每个用例独立落盘文件，避免用例间互相污染。"""
        self.tmp = tempfile.mkdtemp(prefix="clients_test_")
        self._orig = registry.REGISTRY_PATH
        registry.REGISTRY_PATH = Path(self.tmp) / "client_registry.json"
        self.app = _build_app()
        self.client = self.app.test_client()

    def tearDown(self):
        """还原落盘路径并清理临时目录。"""
        registry.REGISTRY_PATH = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _register(self, key="glm", config=None, commands=None):
        """发起一次注册请求，返回响应对象。"""
        return self.client.post("/api/clients", json={
            "site_key": key,
            "custom_config": _RICH_CONFIG if config is None else config,
            "commands": _COMMANDS if commands is None else commands,
        })

    def _lookup(self, key="glm"):
        """发起一次取回请求，返回响应对象。"""
        return self.client.get("/api/clients", query_string={"site_key": key})

    def _unregister(self, key="glm"):
        """发起一次注销请求，返回响应对象。"""
        return self.client.delete("/api/clients", query_string={"site_key": key})

    def test_register_then_lookup_byte_identical(self):
        """注册后取回：自定义配置与存入时逐字节一致，指令声明原样带回。"""
        r = self._register()
        self.assertEqual(200, r.status_code)
        self.assertTrue(r.get_json()["success"])
        body = self._lookup().get_json()
        self.assertTrue(body["success"])
        # 深比较：结构、类型、值全部一致。
        self.assertEqual(_RICH_CONFIG, body["custom_config"])
        # 逐字节一致：按同一规则序列化后比较 UTF-8 字节串。
        expected = json.dumps(_RICH_CONFIG, ensure_ascii=False, sort_keys=True).encode("utf-8")
        actual = json.dumps(body["custom_config"], ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.assertEqual(expected, actual)
        self.assertEqual(_COMMANDS, body["commands"])

    def test_duplicate_register_overrides(self):
        """同一 site_key 重复注册：后者整条覆盖前者，不追加。"""
        self._register()
        other = {"只留": ["这一项"], "数值": None}
        r = self._register(config=other, commands=[])
        self.assertEqual(200, r.status_code)
        body = self._lookup().get_json()
        self.assertEqual(other, body["custom_config"])
        self.assertEqual([], body["commands"])

    def test_lookup_unregistered_returns_error(self):
        """取回未注册标识：返回明确错误（404 + success=false）。"""
        r = self._lookup("never-registered")
        self.assertEqual(404, r.status_code)
        body = r.get_json()
        self.assertFalse(body["success"])
        self.assertIn("未注册", body["error"])

    def test_lookup_after_unregister_returns_error(self):
        """注销后取回：返回明确错误。"""
        self._register()
        r = self._unregister()
        self.assertTrue(r.get_json()["removed"])
        r2 = self._lookup()
        self.assertEqual(404, r2.status_code)
        self.assertFalse(r2.get_json()["success"])

    def test_unregister_missing_is_ok(self):
        """注销不存在的标识：不报错，removed=false。"""
        r = self._unregister("nope")
        self.assertEqual(200, r.status_code)
        body = r.get_json()
        self.assertTrue(body["success"])
        self.assertFalse(body["removed"])

    def test_restart_persists(self):
        """重启后取回：重新导入模块（等价重启）仍读到同一份落盘内容。"""
        self._register()
        # 重新导入会重置模块级路径，先记下本用例的临时落盘位置。
        tmp_path = registry.REGISTRY_PATH
        reloaded = importlib.reload(registry)
        reloaded.REGISTRY_PATH = tmp_path
        entry = reloaded.lookup("glm")
        self.assertIsNotNone(entry)
        self.assertEqual(_RICH_CONFIG, entry["custom_config"])
        # 经接口取回同样一致：证明路由层读的也是落盘数据，而非内存缓存。
        body = self._lookup().get_json()
        self.assertEqual(_RICH_CONFIG, body["custom_config"])
        self.assertTrue(Path(tmp_path).exists())

    def test_site_key_with_special_chars(self):
        """标识含斜杠、问号、与号与中文时，取回仍准确。"""
        key = "https://chatglm.cn/a?b=1&c=中文"
        self._register(key=key, config={"x": 1})
        body = self._lookup(key).get_json()
        self.assertTrue(body["success"])
        self.assertEqual({"x": 1}, body["custom_config"])
