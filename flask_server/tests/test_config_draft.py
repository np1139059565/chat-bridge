import tempfile, unittest
from pathlib import Path
from flask import Flask
from routes import config_route as cr

class TestConfigDraft(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = cr.DRAFT_PATH
        cr.DRAFT_PATH = Path(self.tmp.name) / "draft.json"
    def tearDown(self):
        cr.DRAFT_PATH = self.old
        self.tmp.cleanup()
    def test_save_load_clear(self):
        self.assertIsNone(cr._load_draft())
        cr._save_draft({"limits": {"max_json_chars": 201}, "pending": [{"block": "bridge"}]})
        d = cr._load_draft()
        self.assertEqual(d["limits"]["max_json_chars"], 201)
        self.assertEqual(len(d["pending"]), 1)
        cr._clear_draft()
        self.assertIsNone(cr._load_draft())
    def test_draft_endpoint_returns_two_copies(self):
        app = Flask(__name__)
        app.register_blueprint(cr.bp)
        c = app.test_client()
        cr._save_draft({"limits": {"max_json_chars": 999}})
        j = c.get("/config/draft").get_json()
        self.assertTrue(j["success"])
        self.assertIn("profiles", j["master"])
        self.assertEqual(j["draft"]["limits"]["max_json_chars"], 999)
        c.post("/config/draft", json={"limits": {"max_json_chars": 202}})
        self.assertEqual(cr._load_draft()["limits"]["max_json_chars"], 202)
    def test_commit_source_audit(self):
        src = Path(cr.__file__).read_text(encoding="utf-8")
        self.assertIn('@bp.route("/config/commit"', src)
        self.assertIn("_clear_draft()", src)
        self.assertIn("def _apply_patch(data)", src)

if __name__ == "__main__":
    unittest.main()
