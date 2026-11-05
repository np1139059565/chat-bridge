"""QQ 推送的会话隔离：测试。

背景（走查发现）：
    修复前，handle_report 的推送用一把**全局**推送锁保护。锁内包含 QQ 网络推送，
    QQ 一慢，这把全局锁就被长时间持有，导致所有会话的推送在这把锁上串行排队——
    一个慢会话拖住全部会话。

修复目标（对准真实行为，而非实现细节）：
    一个会话的慢推送，不得阻塞其它会话的推送；同一会话内部仍需串行，
    以保证去重与顺序不乱。

测试分三类：
    1. 跨会话不互相阻塞（本次修复的核心）；
    2. 同会话去重仍生效（防回归）；
    3. 同会话顺序保持（防回归）。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_message_router_lock -v
"""
import os
import sys
import threading
import time
import unittest
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 本目录也要在路径上：共享夹具与本文件同级，单跑时靠这一行才能导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths  # noqa: F401
from remote_bridge import message_router as mr
from message_router_fixtures import RouterTestBase

# 共享夹具已提供存储模拟与打补丁，本文件只需沿用；
# 与窗口那份的差异仅在于窗口那份还要隔离模块级状态。
_Base = RouterTestBase


class TestCrossConversationIsolation(_Base):
    """跨会话：一个慢会话不得阻塞其它会话的推送。"""

    def test_slow_conv_does_not_block_other_conv(self):
        started_b = []

        def _push_text(qq_client, openid, text, markdown=False):
            if "AAA" in text:
                time.sleep(0.5)          # 会话 A 的推送很慢
            if "BBB" in text:
                started_b.append(time.time())
            return True

        mr.push_text = _push_text
        t0 = time.time()

        ta = threading.Thread(
            target=lambda: mr.handle_report(object(), self._payload("convA", "mA", "AAA")))
        ta.start()
        time.sleep(0.05)                 # 确保 A 先进入推送
        tb = threading.Thread(
            target=lambda: mr.handle_report(object(), self._payload("convB", "mB", "BBB")))
        tb.start()
        ta.join()
        tb.join()

        self.assertTrue(started_b, "会话 B 的推送未执行")
        self.assertLess(
            started_b[0] - t0, 0.4,
            "会话 B 被会话 A 的慢推送阻塞了（疑似仍用全局锁）",
        )


class TestSameConversationSerial(_Base):
    """同会话：去重与顺序仍需保持。"""

    def test_dedup_same_conv(self):
        """同一消息第二次上报不应重复推送。"""
        count = [0]

        def _push_text(qq_client, openid, text, markdown=False):
            count[0] += 1
            return True

        mr.push_text = _push_text
        payload = self._payload("conv-d", "m1", "hi")
        mr.handle_report(object(), payload)
        mr.handle_report(object(), payload)
        self.assertEqual(count[0], 1, "去重失效：同一条被推了多次")

    def test_order_same_conv(self):
        """同一会话内，多条消息的推送顺序应与消息顺序一致。"""
        order = []

        def _push_text(qq_client, openid, text, markdown=False):
            order.append(text)
            return True

        mr.push_text = _push_text
        payload = {
            "conversationId": "conv-o",
            "openid": "user-1",
            "messages": [
                {"id": "o1", "source": "assistant", "md": "first"},
                {"id": "o2", "source": "assistant", "md": "second"},
                {"id": "o3", "source": "assistant", "md": "third"},
            ],
        }
        mr.handle_report(object(), payload)
        joined = "\n".join(order)
        pos = [joined.find(k) for k in ("first", "second", "third")]
        self.assertTrue(all(p >= 0 for p in pos), "有消息未推送")
        self.assertEqual(pos, sorted(pos), "同会话推送顺序错乱")


if __name__ == "__main__":
    unittest.main()
