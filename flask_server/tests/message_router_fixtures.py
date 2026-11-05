"""message_router 测试的共享夹具

为什么需要：两份测试（锁隔离、被动回复窗口）各自复制了一份「模拟存储 + 打补丁」的脚手架，
内容逐字相同。任一处调整都要改两遍，漏改会让两份测试的前置环境悄悄分叉。
抽到此处后，存储模拟与基础打补丁只有一份真源。

差异留在子类：窗口那份还需要隔离模块级可变状态（窗口表、最近用户等），
通过覆盖 extra_patches() 追加，而不是复制整段 setUp。

命名约定：文件名不以 test_ 开头，测试发现不会误把它当成用例文件。
"""
import os
import sys
import unittest
import unittest.mock as mock

# 与两份测试相同的路径引导：把 flask_server 加进导入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from remote_bridge import message_router as mr  # noqa: E402


class StoreMock:
    """按会话隔离地模拟 bridge_store 的推送相关读写。

    pushed：conv_id -> 已推送键集合
    pending：conv_id -> 待推消息列表
    """

    def __init__(self):
        self.pushed = {}
        self.pending = {}

    def get_config(self):
        """推送开关全开，避免用例受真实配置影响。"""
        return {"push": {"user": True, "tool": True, "ai": True}}

    def get_pushed_set(self, conv_id):
        """返回该会话已推送键的副本，调用方改动不回写。"""
        return set(self.pushed.get(conv_id, set()))

    def mark_pushed(self, conv_id, keys):
        """登记该会话已推送的键。"""
        self.pushed.setdefault(conv_id, set()).update(keys)

    def set_pending(self, conv_id, failed):
        """覆盖该会话的待推缓存。"""
        self.pending[conv_id] = list(failed)

    def merge_pending(self, conv_id, msgs):
        """原样返回传入消息（本测试不验证补推合并细节）。"""
        return list(msgs)


class RouterTestBase(unittest.TestCase):
    """公共夹具：替换 bridge_store 的推送相关读写。

    子类如需追加补丁（例如隔离模块级状态），覆盖 extra_patches() 返回补丁列表，
    基类会在基础补丁之后一并启动、并在清理时逆序停止。
    """

    def setUp(self):
        """启动基础补丁，并记录原始的 push_text 以便还原。"""
        self.store = StoreMock()
        self._patches = [
            mock.patch.object(mr.bridge_store, "get_config", self.store.get_config),
            mock.patch.object(mr.bridge_store, "get_pushed_set", self.store.get_pushed_set),
            mock.patch.object(mr.bridge_store, "mark_pushed", self.store.mark_pushed),
            mock.patch.object(mr.bridge_store, "set_pending", self.store.set_pending),
            mock.patch.object(mr.bridge_store, "merge_pending", self.store.merge_pending),
        ]
        # 子类追加的补丁接在后面，保持「基础在前、扩展在后」的顺序
        self._patches += self.extra_patches()
        for p in self._patches:
            p.start()
        # push_text 是被直接赋值的模块属性，不走 mock，需手动备份
        self._orig_push_text = mr.push_text

    def extra_patches(self):
        """子类可覆盖：返回需要追加的补丁列表。

        @returns mock.patch 对象列表；默认无
        """
        return []

    def tearDown(self):
        """还原 push_text 并逆序停止全部补丁。"""
        mr.push_text = self._orig_push_text
        for p in reversed(self._patches):
            p.stop()

    @staticmethod
    def _payload(conv, mid, body):
        """构造一条上报体：单个会话、单条助手消息。

        @param conv 会话 id
        @param mid  消息 id
        @param body 正文
        @returns 上报体字典
        """
        return {
            "conversationId": conv,
            "openid": "user-1",
            "messages": [{"id": mid, "source": "assistant", "md": body}],
        }
