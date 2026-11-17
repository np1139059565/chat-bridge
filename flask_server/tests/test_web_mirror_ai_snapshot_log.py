"""AI 快照观测埋点：接进 _build_item、只打日志、不改判定。

为 B2 提供实机对照素材：同一条回复生成中/完成态的 id、key、len、head。
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from web_bridge import web_mirror  # noqa: E402


class TestAiSnapshotLog(unittest.TestCase):
    def test_log_contains_identity_fields(self):
        calls = []
        orig = web_mirror.app_log.debug
        web_mirror.app_log.debug = lambda *a: calls.append(a)
        try:
            web_mirror._log_ai_snapshot("mABC", "p-mABC", "完整正文")
        finally:
            web_mirror.app_log.debug = orig
        self.assertEqual(len(calls), 1)
        joined = " ".join(str(x) for x in calls[0])
        self.assertIn("mABC", joined)
        self.assertIn("p-mABC", joined)
        self.assertIn("len=4", joined)
        self.assertIn("完整正文", joined)

    def test_build_item_emits_snapshot_for_ai(self):
        with mock.patch.object(web_mirror, "_gate", return_value=("m1", None, "ai")), \
             mock.patch.object(web_mirror, "_compose_body", return_value="BODY"), \
             mock.patch.object(web_mirror, "_finalize_body", side_effect=lambda b, e, p: b), \
             mock.patch.object(web_mirror, "_prepare_fields", return_value=("", "", "ai")), \
             mock.patch.object(web_mirror, "_log_ai_snapshot") as snap:
            it = web_mirror._build_item({"key": "p-m1"}, {}, {})
        self.assertEqual(it["source_id"], "m1")
        self.assertEqual(it["key"], "p-m1")
        snap.assert_called_once_with("m1", "p-m1", "BODY")

    def test_non_ai_emits_no_snapshot(self):
        with mock.patch.object(web_mirror, "_gate", return_value=("u1", None, "user")), \
             mock.patch.object(web_mirror, "_compose_body", return_value="hi"), \
             mock.patch.object(web_mirror, "_finalize_body", side_effect=lambda b, e, p: b), \
             mock.patch.object(web_mirror, "_prepare_fields", return_value=("", "", "user")), \
             mock.patch.object(web_mirror, "_log_ai_snapshot") as snap:
            web_mirror._build_item({}, {}, {})
        snap.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)