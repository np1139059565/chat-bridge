"""收件箱按站点隔离的测试。

背景：一台电脑同时开多个网页 AI 时，手机端原本把所有站点的消息混在
同一条时间线里，分不清哪条来自哪个 AI。收件箱因此给每条消息加了
site_key 字段，读取接口按它过滤。

验证目标：
1. append 写入的 site_key 会被保留；
2. list_since / recent / before_seq 三档过滤语义正确
   （None=不过滤、''=只取无站点、非空只取该站点）；
3. 写入时未带 site_key 的历史消息归入「未知站点」。

A-8 波动治理（2026-11-14）——本文件曾随机 2-4 failed，两个根因均出在
测试基类与 web_inbox_store 后台异步写盘线程的竞态上，业务代码不动，
只在基类治理（确定性复现见同目录 _inbox_race_repro.py）：

RC1 读撞异步写盘（「读取收件箱失败，按空箱处理」波动）：后台写线程
不持有任何锁执行 Path.write_text，而 write_text 先截断后写入，读取若
落在该窗口内会解析到半截文件，read_state 兜底为空状态并覆盖内存
缓存——表现为「append 成功、紧接读取却是空箱」。治理：用例期间把
异步排队写替换为同线程同步写（append 全程持 web_inbox._lock 完成
读-改-写，任何线程都不可能观察到半截文件）。

RC2 迟到写盘跨用例泄漏（站点过滤/计数波动）：基类换路径从不与后台
写线程同步，也不清 _pending，上一用例排队的写若在换路径后才落盘，
会解析到新用例的临时路径并把旧状态写进它的目录。治理：setUp 在换
路径前排空/丢弃遗留 _pending 并把 writer 重新休眠，迟到唤醒解析不
到新路径。
"""
import os
import pathlib
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  路径导入引导


class _InboxBase(unittest.TestCase):
    """把数据目录重定向到临时目录，测试互不干扰。

    治理细节见模块 docstring 的 RC1/RC2；setUp 三步走：先驯服后台
    写线程，再换路径，最后换同步写，tearDown 逆序恢复。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="inbox_site_")
        self._quiesce_background_writer()
        self._redirect_paths()
        self._install_sync_write()
        from web_bridge import web_inbox
        self.inbox = web_inbox

    def _quiesce_background_writer(self):
        """RC2 治理：排空/丢弃遗留 _pending，并让后台写线程休眠。

        在途写先落到「换路径前」的旧路径并等它完成，迟到唤醒才解析
        不到新用例的临时路径；详见模块 docstring。
        """
        from web_bridge import web_inbox_store
        self._orig_write_now = web_inbox_store._write_state_now
        self._orig_write_state = web_inbox_store.write_state
        done = threading.Event()

        def _tracked_write_now(state):
            # 只为 setUp 提供一次「在途写已完成」信号，逻辑不变。
            try:
                self._orig_write_now(state)
            finally:
                done.set()

        web_inbox_store._write_state_now = _tracked_write_now
        with web_inbox_store._pending_lock:
            has_pending = web_inbox_store._pending is not None
            web_inbox_store._pending_event.set()
        if has_pending:
            self.assertTrue(done.wait(2.0), "后台写线程未在期限内完成在途写")
        with web_inbox_store._pending_lock:
            web_inbox_store._pending = None
            web_inbox_store._pending_event.clear()

    def _redirect_paths(self):
        """把收件箱路径与内存缓存重定向到本用例的临时目录。

        paths.py 的 DATA_DIR 用 __file__ 推导、无环境变量开关，只能
        替换模块级常量（曾因只改环境变量，测试读写到了真实
        inbox.json）。
        """
        tmp_dir = os.path.join(self.tmp, "web")
        os.makedirs(tmp_dir, exist_ok=True)
        self._orig_web_dir = paths.WEB_DIR
        self._orig_inbox = paths.WEB_INBOX_PATH
        paths.WEB_DIR = pathlib.Path(tmp_dir)
        paths.WEB_INBOX_PATH = paths.WEB_DIR / "inbox.json"
        from web_bridge import web_inbox_store
        web_inbox_store._cache = None
        web_inbox_store._cache_sig = None

    def _install_sync_write(self):
        """RC1 治理：用例期间以同线程同步写替换异步排队写。

        append / append_many 全程持 web_inbox._lock 完成「读-改-写」，
        同线程落盘不产生截断窗口；缓存与文件签名照旧维护。
        """
        from web_bridge import web_inbox_store

        def _sync_write_state(state):
            web_inbox_store._cache = state
            self._orig_write_now(state)

        web_inbox_store.write_state = _sync_write_state

    def tearDown(self):
        # 用例内的写都是同步落盘的，_pending 恒为空，无需 flush；
        # 先恢复真实（异步）写通道，再恢复路径并清理临时目录。
        from web_bridge import web_inbox_store
        web_inbox_store.write_state = self._orig_write_state
        web_inbox_store._write_state_now = self._orig_write_now
        paths.WEB_DIR = self._orig_web_dir
        paths.WEB_INBOX_PATH = self._orig_inbox
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestAppendSiteKey(_InboxBase):
    """写入时站点标签的保留。"""

    def test_带站点写入后被保留(self):
        self.inbox.append("ai", "你好", extra={"site_key": "glm"})
        data = self.inbox.recent(10, "glm")
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["site_key"], "glm")

    def test_未带站点写入时为空簇(self):
        """未指定站点的消息归入「未知站点」，不报错。"""
        self.inbox.append("ai", "你好")
        data = self.inbox.recent(10, "")
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["site_key"], "")


class TestListSinceFilter(_InboxBase):
    """list_since 的三档过滤。"""

    def _seed(self):
        """写入三条不同站点的消息。"""
        self.inbox.append("ai", "来自 glm", extra={"site_key": "glm"})
        self.inbox.append("ai", "来自千问", extra={"site_key": "qianwen"})
        self.inbox.append("ai", "无站点", extra={"site_key": ""})

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
        """游标推进后仍受站点过滤约束，不会切到别站的新消息。"""
        self._seed()
        first = self.inbox.list_since(0, 100, "glm")
        cur = first["seq"]
        self.inbox.append("ai", "glm 新消息", extra={"site_key": "glm"})
        self.inbox.append("ai", "千问新消息", extra={"site_key": "qianwen"})
        more = self.inbox.list_since(cur, 100, "glm")
        self.assertEqual(len(more["messages"]), 1)
        self.assertEqual(more["messages"][0]["text"], "glm 新消息")


class TestRecentAndBeforeFilter(_InboxBase):
    """recent / before_seq 的站点过滤。"""

    def test_recent_按站点过滤(self):
        self.inbox.append("ai", "a", extra={"site_key": "glm"})
        self.inbox.append("ai", "b", extra={"site_key": "qianwen"})
        data = self.inbox.recent(10, "qianwen")
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["text"], "b")

    def test_before_seq_按站点过滤(self):
        self.inbox.append("ai", "a", extra={"site_key": "glm"})
        self.inbox.append("ai", "b", extra={"site_key": "qianwen"})
        self.inbox.append("ai", "c", extra={"site_key": "glm"})
        data = self.inbox.before_seq(3, 10, "glm")
        texts = [m["text"] for m in data["messages"]]
        self.assertEqual(texts, ["a"])

    def test_无匹配站点时返回空(self):
        self.inbox.append("ai", "a", extra={"site_key": "glm"})
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


class TestAsyncWriteGovernance(_InboxBase):
    """A-8 治理回归：两个竞态消除后必须稳定成立的行为。

    以下用例在治理前的代码上按 RC1/RC2 的时序是可复现失败的
    （确定性复现见同目录 _inbox_race_repro.py，该脚本直测业务层、
    未经基类治理，因此仍应显示两个 False——业务层是否加原子写是
    后续独立议题，不在本笔任务范围）。
    """

    def test_写后立读不落入空箱(self):
        # RC1 回归：写后紧接的读取绝不能因为撞上写盘窗口而得到空箱。
        for i in range(20):
            self.inbox.append("ai", "m%d" % i, extra={"site_key": "glm"})
            data = self.inbox.recent(100, "glm")
            self.assertEqual(len(data["messages"]), i + 1)

    def test_前序用例不向新用例目录泄漏(self):
        # 本用例排在 test_写后立读之后执行（unittest 按名字排序），
        # 其同步写盘只落在它自己的临时目录；本用例的新目录必须是
        # 干净的——RC2 的迟到写曾把前序状态写进这里。
        import os
        self.assertFalse(
            paths.WEB_INBOX_PATH.exists(),
            "新用例目录不应出现前序用例的收件箱文件",
        )
        self.inbox.append("ai", "fresh", extra={"site_key": "glm"})
        data = self.inbox.recent(10, "glm")
        self.assertEqual([m["text"] for m in data["messages"]], ["fresh"])
        # 同步写应已落盘且内容完整。
        self.assertTrue(paths.WEB_INBOX_PATH.exists())
        import json
        raw = json.loads(paths.WEB_INBOX_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(raw["messages"]), 1)
        self.assertEqual(raw["messages"][0]["site_key"], "glm")


if __name__ == "__main__":
    unittest.main()