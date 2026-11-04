"""卡片关键字段的存取往返测试

背景（现场日志）：
    [卡片诊断] 重判：树内卡片=285 工具卡=0 待判定=0 恢复=0 缺字段=0 签名库=29

树里有 285 张卡，却没有一张被认作工具卡。根因是 cards 表只存了
node_id / block_id / tool / status / result / finished_at 六个字段，
前端渲染赖以判断的 isTool、msgId、parameters、executed 从未入库。
从后端恢复的卡片因此全是「没有工具身份的空壳」，渲染成普通代码块。

本文件钉住一件事：卡片存进库再取出来，关键字段必须原样还在。

运行：python -m pytest tests/test_memory_cards_roundtrip.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import memory_cards
import memory_nodes
from tests.memory_db_base import MemoryDBTestBase


def _mk_node(msg_id):
    """写入一个最简节点，供卡片挂靠。

    @param msg_id 消息指纹
    @returns 节点数据库 id
    """
    return memory_nodes.upsert_node(
        {"msg_id": msg_id, "conv_id": "c1", "site_key": "s1"},
        {"source": "assistant", "role": "assistant", "name": "ai", "blocks": []},
    )


class TestCardRoundtrip(MemoryDBTestBase):
    """卡片存入再取出，关键字段不能丢。"""

    PREFIX = "memcards_rt_"

    def test_is_tool_survives_roundtrip(self):
        """isTool 必须能存能取——它是渲染成工具卡片的唯一依据。"""
        nid = _mk_node("m1")
        memory_cards.upsert_card(nid, "b1", tool="read_file", status="pending",
                                 is_tool=True)
        cards = memory_cards.list_by_node(nid)
        self.assertEqual(len(cards), 1)
        # 取出来的卡片必须仍被认作工具卡片
        self.assertIs(cards[0]["isTool"], True)

    def test_msg_id_survives_roundtrip(self):
        """msgId 必须能存能取——执行签名靠它拼接。"""
        nid = _mk_node("m1")
        memory_cards.upsert_card(nid, "b1", tool="t", status="pending",
                                 msg_id="msg-abc")
        self.assertEqual(memory_cards.list_by_node(nid)[0]["msgId"], "msg-abc")

    def test_parameters_survive_roundtrip(self):
        """parameters 必须能存能取——重新执行要用原始参数。"""
        nid = _mk_node("m1")
        params = {"path": "a.txt", "count": 3}
        memory_cards.upsert_card(nid, "b1", tool="t", status="pending",
                                 parameters=params)
        self.assertEqual(memory_cards.list_by_node(nid)[0]["parameters"], params)

    def test_executed_survives_roundtrip(self):
        """executed 必须能存能取——它决定按钮显示「执行」还是「重新执行」。"""
        nid = _mk_node("m1")
        memory_cards.upsert_card(nid, "b1", tool="t", status="done",
                                 executed=True)
        self.assertIs(memory_cards.list_by_node(nid)[0]["executed"], True)

    def test_full_card_roundtrip(self):
        """完整卡片：一次写入全部字段，逐个比对。"""
        nid = _mk_node("m1")
        memory_cards.upsert_card(
            nid, "b1", tool="run_command", status="done",
            result={"ok": True}, finished_at=1700000000,
            is_tool=True, msg_id="msg-1",
            parameters={"cmd": "ls"}, executed=True)
        c = memory_cards.list_by_node(nid)[0]
        self.assertIs(c["isTool"], True)
        self.assertEqual(c["msgId"], "msg-1")
        self.assertEqual(c["parameters"], {"cmd": "ls"})
        self.assertIs(c["executed"], True)
        # 原有字段不受影响
        self.assertEqual(c["tool"], "run_command")
        self.assertEqual(c["status"], "done")
        self.assertEqual(c["result"], {"ok": True})

    def test_null_fields_tolerated(self):
        """缺省字段不报错：老卡片没有这些列时也要能读出来。"""
        nid = _mk_node("m1")
        memory_cards.upsert_card(nid, "b1", tool="t", status="pending")
        c = memory_cards.list_by_node(nid)[0]
        self.assertEqual(c["tool"], "t")
        self.assertFalse(c.get("isTool"))
