"""web_inbox 去重：内容级判重集合持久化 + role 集合与文档对齐。

回归 P3：messages / seen 都被限长截断后，刷新重放的旧消息重新入库，
表现为老消息排到新消息后面（图 4 的 10:13 / 10:27）。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from web_bridge import web_inbox  # noqa: E402


class TestContentSeenPersist(unittest.TestCase):
    def test_init_batch_reads_persisted_content_seen(self):
        state = {"seq": 0, "messages": [], "seen": [],
                 "content_seen": [["ai", "旧正文"]]}
        b = web_inbox._init_batch(state)
        self.assertIn(("ai", "旧正文"), b["content_seen"])

    def test_old_replay_skipped_after_truncation(self):
        # 旧消息已从 messages 与 seen 里被截断，只有持久化的判重集合还在
        state = {"seq": 0, "messages": [], "seen": [],
                 "content_seen": [["ai", "完整正文"]]}
        b = web_inbox._init_batch(state)
        it = {"source_id": "old-fingerprint", "role": "ai",
              "text": "完整正文"}
        self.assertTrue(web_inbox._skip_item(it, b["seen"], b["content_seen"]))

    def test_legacy_state_falls_back_to_messages(self):
        state = {"seq": 0,
                 "messages": [{"role": "ai", "text": "A"}], "seen": []}
        b = web_inbox._init_batch(state)
        self.assertIn(("ai", "A"), b["content_seen"])

    def test_flush_batch_persists_content_seen(self):
        state = {"seq": 0, "messages": [], "seen": []}
        b = web_inbox._init_batch(state)
        b["content_seen"].add(("ai", "X"))
        b["added"] = [object()]
        orig = web_inbox._write_state
        web_inbox._write_state = lambda s: None
        try:
            web_inbox._flush_batch(state, b)
        finally:
            web_inbox._write_state = orig
        self.assertEqual(state.get("content_seen"), [["ai", "X"]])

    def test_system_reply_not_swallowed_by_content_dedup(self):
        cs = {("system", "已下发")}
        it = {"source_id": "", "role": "system", "text": "已下发"}
        self.assertFalse(web_inbox._skip_item(it, set(), cs))

    def test_same_ai_text_still_deduped_within_batch(self):
        b = web_inbox._init_batch({"seq": 0, "messages": [], "seen": []})
        it = {"source_id": "fp", "role": "ai", "text": "同一段"}
        self.assertFalse(web_inbox._skip_item(it, b["seen"], b["content_seen"]))
        b["content_seen"].add(("ai", "同一段"))
        self.assertTrue(web_inbox._skip_item(it, b["seen"], b["content_seen"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)