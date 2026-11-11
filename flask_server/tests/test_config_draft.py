import tempfile, unittest
from pathlib import Path
from flask import Flask
import config_draft_store as ds
from routes import config_route as cr

class TestConfigDraft(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = ds._DRAFT_DIR
        ds._DRAFT_DIR = Path(self.tmp.name)
    def tearDown(self):
        ds._DRAFT_DIR = self.old
        self.tmp.cleanup()
    def test_site_isolation(self):
        self.assertIsNone(ds.load("yuanbao.tencent.com"))
        ds.save("yuanbao.tencent.com", {"limits": {"max_json_chars": 201}})
        self.assertEqual(ds.load("yuanbao.tencent.com")["limits"]["max_json_chars"], 201)
        self.assertIsNone(ds.load("chatglm.cn"), "B 页面读到了 A 页面草稿")
        ds.save("chatglm.cn", {"limits": {"max_json_chars": 999}})
        self.assertEqual(ds.load("yuanbao.tencent.com")["limits"]["max_json_chars"], 201)
        self.assertEqual(ds.load("chatglm.cn")["limits"]["max_json_chars"], 999)
        ds.clear("yuanbao.tencent.com")
        self.assertIsNone(ds.load("yuanbao.tencent.com"))
        self.assertEqual(ds.load("chatglm.cn")["limits"]["max_json_chars"], 999)
    def test_endpoint_master_unique_draft_per_site(self):
        app = Flask(__name__); app.register_blueprint(cr.bp); c = app.test_client()
        ds.save("a.com", {"limits": {"max_json_chars": 7}})
        j = c.get("/config/draft", headers={"X-Site-Key": "a.com"}).get_json()
        self.assertEqual(j["site"], "a.com")
        self.assertIn("profiles", j["master"])
        self.assertEqual(j["draft"]["limits"]["max_json_chars"], 7)
        j2 = c.get("/config/draft", headers={"X-Site-Key": "b.com"}).get_json()
        self.assertIsNone(j2["draft"], "B 页面读到了 A 页面草稿")
        self.assertEqual(j2["master"], j["master"], "母版必须唯一一份")
    def test_post_apply_to_runtime_no_yaml(self):
        import runtime
        old = runtime.CONFIG.get("limits", {}).get("max_json_chars")
        try:
            app = Flask(__name__); app.register_blueprint(cr.bp); c = app.test_client()
            r = c.post("/config/draft", json={"limits": {"max_json_chars": 321}}, headers={"X-Site-Key": "a.com"})
            self.assertTrue(r.get_json()["success"])
            self.assertEqual(runtime.CONFIG["limits"]["max_json_chars"], 321, "改完未即时生效")
            self.assertEqual(ds.load("a.com")["limits"]["max_json_chars"], 321)
            src = Path(ds.__file__).read_text(encoding="utf-8")
            self.assertNotIn("save_config_to_yaml(", src, "草稿生效不应写母版")
        finally:
            if old is not None:
                runtime.CONFIG.setdefault("limits", {})["max_json_chars"] = old
    def test_commit_source_audit(self):
        src = Path(cr.__file__).read_text(encoding="utf-8")
        self.assertIn('@bp.route("/config/commit"', src)
        self.assertIn("draft_store.clear(_site_of())", src)
        self.assertIn("X-Site-Key", src)
        self.assertIn("draft_store.load(site)", src)

if __name__ == "__main__":
    unittest.main()
