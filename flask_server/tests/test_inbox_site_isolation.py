"""收件箱按站点隔离的测试。

背景：一台电脑同时开多个网页 AI 时，手机端原本把所有站点的消息混在
同一条时间线里，分不清哪条来自哪个 AI。收件箱因此给每条消息加了
site_key 字段，读取接口按它过滤。

验证目标：
1. append 写入的 site_key 会被保留；
2. list_since / recent / before_seq 三态过滤语义正确
   （None=不过滤、''=只取无站点、非空=只取该站点）；
3. 写入时未带 site_key 的历史消息归入「未知站点」。
"""
import importlib
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导


class _InboxBase(unittest.TestCase):
    """把数据目录重定向到临时目录，测试互不干扰。"""

    def setUp(self):
        # paths.py 的 DATA_DIR 由 __file__ 推导，没有环境变量开关，
        # 故直接替换模块级路径常量指向临时目录——这是唯一能保证
        # 测试不碰真实数据的方式（曾因只改环境变量，测试读写到了真实 inbox.json）。
        self.tmp = tempfile.mkdtemp(prefix="inbox_site_")
        import paths
        self._orig_web_dir = paths.WEB_DIR
        self._orig_inbox = paths.WEB_INBOX_PATH
        tmp_dir = os.path.join(self.tmp, "web")
        os.makedirs(tmp_dir, exist_ok=True)
        paths.WEB_DIR = __import__("pathlib").Path(tmp_dir)
        paths.WEB_INBOX_PATH = paths.WEB_DIR / "inbox.json"
        from web_bridge import web_inbox_store
        # 清空缓存：否则会复用上一个用例的内存状态
        web_inbox_store._cache = None
        web_inbox_store._cache_sig = None
        from web_bridge import web_inbox
        self.inbox = web_inbox

    def tearDown(self):
        import paths
        paths.WEB_DIR = self._orig_web_dir
        paths.WEB_INBOX_PATH = self._orig_inbox
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestAppendSiteKey(_InboxBase):
    """写入时站点标签的保留。"""

    def test_带站点写入后被保留(self):
        self.inbox.append("ai", "你好", site_key="glm")
        data = self.inbox.recent(10, "glm")
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["site_key"], "glm")

    def test_未带站点写入时为空串(self):
        """未指定站点的消息归入「未知站点」，不报错。"""
        self.inbox.append("ai", "你好")
        data = self.inbox.recent(10, "")
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["site_key"], "")


class TestListSinceFilter(_InboxBase):
    """list_since 的三态过滤。"""

    def _seed(self):
        """写入三条不同站点的消息。"""
        self.inbox.append("ai", "来自 glm", site_key="glm")
        self.inbox.append("ai", "来自千问", site_key="qianwen")
        self.inbox.append("ai", "无站点", site_key="")

    def test_不传站点时不过滤(self):
        """None 表示不过滤——保持向后兼容。"""
        self._seed()
        data = self.inbox.list_since(0, 100)
        self.assertEqual(len(data["messages"]), 3)

    def test_传站点时只返回该站点(self):
        self._seed()
        data = self.inbox.list_since(0, 100, "glm")
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["text"], "来自 glm")

    def test_传空串时只返回无站点消息(self):
        self._seed()
        data = self.inbox.list_since(0, 100, "")
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["text"], "无站点")

    def test_游标与站点过滤同时生效(self):
        """游标推进后仍受站点过滤约束，不会因切站看到别的站新消息。"""
        self._seed()
        first = self.inbox.list_since(0, 100, "glm")
        cur = first["seq"]
        self.inbox.append("ai", "glm 新消息", site_key="glm")
        self.inbox.append("ai", "千问新消息", site_key="qianwen")
        more = self.inbox.list_since(cur, 100, "glm")
        self.assertEqual(len(more["messages"]), 1)
        self.assertEqual(more["messages"][0]["text"], "glm 新消息")


class TestRecentAndBeforeFilter(_InboxBase):
    """recent / before_seq 的站点过滤。"""

    def test_recent_按站点过滤(self):
        self.inbox.append("ai", "a", site_key="glm")
        self.inbox.append("ai", "b", site_key="qianwen")
        data = self.inbox.recent(10, "qianwen")
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["text"], "b")

    def test_before_seq_按站点过滤(self):
        self.inbox.append("ai", "a", site_key="glm")
        self.inbox.append("ai", "b", site_key="qianwen")
        self.inbox.append("ai", "c", site_key="glm")
        data = self.inbox.before_seq(3, 10, "glm")
        texts = [m["text"] for m in data["messages"]]
        self.assertEqual(texts, ["a"])

    def test_无匹配站点时返回空(self):
        self.inbox.append("ai", "a", site_key="glm")
        data = self.inbox.recent(10, "kimi")
        self.assertEqual(data["messages"], [])


class TestAppendManySiteKey(_InboxBase):
    """批量入库时的站点标签。"""

    def test_批量条目各自带站点(self):
        items = [
            {"source_id": "s1", "role": "ai", "text": "x", "site_key": "glm"},
            {"source_id": "s2", "role": "ai", "text": "y", "site_key": "qianwen"},
        ]
        self.inbox.append_many(items)
        self.assertEqual(len(self.inbox.recent(10, "glm")["messages"]), 1)
        self.assertEqual(len(self.inbox.recent(10, "qianwen")["messages"]), 1)


if __name__ == "__main__":
    unittest.main()
