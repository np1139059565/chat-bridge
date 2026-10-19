"""QQ 被动回复窗口与上报落点：回归测试。

背景（两次真实事故）：
    1. 删除落盘函数后，message_router 里仍残留一处对它的调用，
       导致每条 QQ 消息进来都抛 AttributeError，note_incoming 中断，
       其后的指令分发与卡片投递全部不再执行——表现为「指令全哑」。
    2. 上报处理缺少「无推送目标」的落点，openid 为空时直接 return，
       消息既没推送也没进待推缓存，等于永久丢失。

本测试锁定的契约（对准真实行为，不依赖内部实现细节）：
    A. 收到 QQ 消息必须能建立窗口，且全过程不抛异常；
    B. 窗口建立后能分配出有效 msg_id 与递增序号；
    C. 推送目标的解析优先级：上报体自带 > 内存中最近发消息的人；
    D. 没有推送目标时，消息必须转入待推缓存（积压），而不是丢弃；
    E. 代码中不得再引用已删除的落盘函数（防止再次漏改调用点）。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_message_router_window -v
"""
import os
import sys
import unittest
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401
from remote_bridge import message_router as mr


class _StoreMock:
    """模拟 bridge_store：只保留推送链路真正用到的读写。"""

    def __init__(self):
        self.pushed = {}    # conv_id -> set(keys)
        self.pending = {}   # conv_id -> list(msg)

    def get_config(self):
        return {"push": {"user": True, "tool": True, "ai": True}}

    def get_pushed_set(self, conv_id):
        return set(self.pushed.get(conv_id, set()))

    def mark_pushed(self, conv_id, keys):
        self.pushed.setdefault(conv_id, set()).update(keys)

    def set_pending(self, conv_id, failed):
        self.pending[conv_id] = list(failed)

    def merge_pending(self, conv_id, msgs):
        return list(msgs)


class _Base(unittest.TestCase):
    """公共夹具：替换存储读写，并清空模块级窗口状态。"""

    def setUp(self):
        self.store = _StoreMock()
        self._patches = [
            mock.patch.object(mr.bridge_store, "get_config", self.store.get_config),
            mock.patch.object(mr.bridge_store, "get_pushed_set", self.store.get_pushed_set),
            mock.patch.object(mr.bridge_store, "mark_pushed", self.store.mark_pushed),
            mock.patch.object(mr.bridge_store, "set_pending", self.store.set_pending),
            mock.patch.object(mr.bridge_store, "merge_pending", self.store.merge_pending),
        ]
        # 状态隔离：把模块级可变状态整体替换成「本用例专属的空副本」，
        # 用例结束由 mock 自动还原为原对象。这样测试只会动到副本，
        # 不会清空真实运行中的窗口与缓存——即使测试与生产同进程也安全。
        self._patches += [
            mock.patch.object(mr, "_windows", {}),
            mock.patch.object(mr, "_last_report", {}),
            mock.patch.object(mr, "_last_openid", ""),
            mock.patch.object(mr, "_last_client", None),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        # 逆序还原：后补的状态副本先还原，避免中途残留半套状态
        for p in reversed(self._patches):
            p.stop()


class TestNoteIncoming(_Base):
    """A/B：收到 QQ 消息必须建立窗口且不抛异常。"""

    def test_note_incoming_creates_window_without_error(self):
        """契约 A：收消息建窗口全过程不抛异常。

        这是事故 1 的直接回归点——当时残留的落盘调用会让本函数抛
        AttributeError，导致后续指令分发全部失效。
        """
        openid, msg_id = "openid-abc", "msg-001"
        # 不捕获异常即视为失败：任何异常都说明调用链被破坏
        mr.note_incoming(openid, msg_id)
        win = mr.get_window(openid)
        self.assertIsNotNone(win, "收消息后窗口未建立")
        self.assertEqual(win["msg_id"], msg_id, "窗口内的消息 id 与入参不符")

    def test_next_seq_increments_within_same_msg(self):
        """契约 B：同一窗口内序号必须递增，不得重复。

        QQ 按 (msg_id, msg_seq) 去重，序号重复会被静默丢弃。
        """
        openid, msg_id = "openid-abc", "msg-002"
        mr.note_incoming(openid, msg_id)
        first = mr.next_seq(openid)
        second = mr.next_seq(openid)
        self.assertEqual(first[0], msg_id)
        self.assertEqual(second[0], msg_id)
        self.assertEqual(first[1] + 1, second[1], "序号未按 1 递增")

    def test_note_incoming_records_client_for_replay(self):
        """收到 QQ 消息时必须记下客户端，补推才发得出去。

        补推依赖 _last_client，而它原先只在网页上报时被赋值。服务重启后
        若用户先发 QQ 指令、网页端尚未上报，补推会因取不到客户端而整段跳过，
        积压消息要等下一次网页上报才推得出去——表现为「指令有回复，但 QQ
        迟迟收不到堆积的消息」。契约：网关收到消息即把客户端交进来。
        """
        sentinel = object()
        mr.note_incoming("openid-abc", "msg-010", sentinel)
        self.assertIs(mr._last_client, sentinel, "收到 QQ 消息后未记录客户端")

    def test_note_incoming_without_client_keeps_existing(self):
        """未传客户端时保留既有引用，不清空。"""
        keep = object()
        mr._last_client = keep
        mr.note_incoming("openid-abc", "msg-011")
        self.assertIs(mr._last_client, keep, "未传客户端时不应清掉既有引用")

    def test_new_message_resets_seq(self):
        """换新 msg_id 时序号从 0 重新计数。"""
        openid = "openid-abc"
        mr.note_incoming(openid, "msg-003")
        mr.next_seq(openid)
        mr.next_seq(openid)
        mr.note_incoming(openid, "msg-004")      # 用户又发了一条
        msg_id, seq = mr.next_seq(openid)
        self.assertEqual(msg_id, "msg-004")
        self.assertEqual(seq, 1, "换新消息后序号应从 1 重新开始")


class TestResolveOpenid(_Base):
    """C：推送目标的解析优先级。"""

    def test_payload_openid_wins(self):
        """上报体自带的 openid 优先于内存兜底值。"""
        mr._last_openid = "from-memory"
        got = mr._resolve_openid({"openid": "from-payload"})
        self.assertEqual(got, "from-payload")

    def test_fallback_to_last_openid(self):
        """上报体没有 openid 时，回退到内存中最近发消息的人。"""
        mr._last_openid = "from-memory"
        got = mr._resolve_openid({})
        self.assertEqual(got, "from-memory")

    def test_both_empty_returns_empty(self):
        """两处都没有时返回空串，由调用方转积压。"""
        self.assertEqual(mr._resolve_openid({}), "")

    def test_web_openid_falls_back_to_qq_user(self):
        """网页端标识不得成为 QQ 推送目标。

        网页端上报固定带 openid=web-user。若照单全收，这个非空值会盖掉
        QQ 用户的窗口键，此后所有推送都查不到窗口而报「窗口已关闭」、
        消息静默丢弃，且网页端每上报一次就重新污染一次，直到重启。
        契约：遇到网页端标识时跳过，回退到最近发来 QQ 消息的用户。
        """
        mr._last_openid = "19501CD1"
        self.assertEqual(mr._resolve_openid({"openid": mr.WEB_OPENID}), "19501CD1")

    def test_web_openid_without_qq_user_returns_empty(self):
        """没有 QQ 用户可回退时返回空串，交由调用方积压。"""
        mr._last_openid = ""
        self.assertEqual(mr._resolve_openid({"openid": mr.WEB_OPENID}), "")


class TestReportWithoutOpenid(_Base):
    """D：无推送目标时必须积压，绝不能丢。"""

    def test_messages_go_to_pending_when_no_openid(self):
        """没有推送目标时，消息进入待推缓存而不是被丢弃。

        这是事故 2 的回归点：此前 openid 为空直接 return，消息永久丢失。
        """
        conv = "conv-no-openid"
        payload = {
            "conversationId": conv,
            "openid": "",                    # 明确没有推送目标
            "messages": [
                {"id": "m1", "source": "assistant", "md": "回复一"},
                {"id": "m2", "source": "assistant", "md": "回复二"},
            ],
        }
        sent = mr.handle_report(object(), payload)
        self.assertEqual(sent, 0, "无目标时不应报告已推送条数")
        self.assertIn(conv, self.store.pending, "消息未进入待推缓存")
        self.assertEqual(len(self.store.pending[conv]), 2, "积压条数与上报不符")


class TestNoStaleDiskReferences(unittest.TestCase):
    """E：防止再次出现「删了函数、调用点没改」。"""

    def test_no_calls_to_removed_disk_functions(self):
        """源码中不得再引用已删除的落盘函数。

        openid 与回复窗口已改为纯内存；若代码里仍残留对
        set_last_openid / get_last_openid / set_last_window /
        get_last_window / restore_window 的调用，运行时会抛 AttributeError，
        且极难在静态检查中发现——故用本用例兜住。
        """
        import inspect
        import re
        src = inspect.getsource(mr)
        # 注意：message_router 自己定义了同名函数 get_last_openid()（纯内存版），
        # 故不能用「子串出现」判定，必须只查「通过 bridge_store 调用」的形式。
        removed = (
            "set_last_openid", "get_last_openid",
            "set_last_window", "get_last_window",
            "restore_window",
        )
        found = []
        for name in removed:
            # 只匹配 bridge_store.<name>( 这种跨模块调用；本模块内的定义不算
            if re.search(r"bridge_store\s*\.\s*%s\s*\(" % name, src):
                found.append(name)
        self.assertFalse(
            found,
            "message_router 仍通过 bridge_store 调用已删除的落盘函数：%s" % found,
        )


class TestStateIsolation(unittest.TestCase):
    """F：测试必须隔离模块状态，不得清空运行中的真实窗口。"""

    def test_setup_replaces_state_with_private_copies(self):
        """用例夹具必须用「替换副本」而不是「清空原对象」。

        同进程运行（或被别的工具导入执行）时，直接 clear 会把生产窗口
        一并抹掉，表现为 QQ 推送突然全部报「窗口已关闭」。
        这里锁死契约：夹具结束后原对象必须还是同一个、内容原样保留。
        """
        # 先写入一份「生产状态」
        mr._windows["prod-openid"] = {"msg_id": "prod-msg", "expire": 9e18, "seq": 0}
        mr._last_report["conv-prod"] = {"conversationId": "conv-prod"}
        origin_windows = mr._windows
        origin_report = mr._last_report

        case = _Base("setUp")
        case.setUp()
        try:
            # 夹具运行期间，被测代码看到的是副本，不是生产对象
            self.assertIsNot(mr._windows, origin_windows, "夹具未替换窗口状态")
            self.assertNotIn("prod-openid", mr._windows, "夹具期间仍能读到生产窗口")
        finally:
            case.tearDown()

        # 夹具结束后：对象与内容都必须原样还原
        self.assertIs(mr._windows, origin_windows, "夹具结束后窗口对象未还原")
        self.assertIn("prod-openid", mr._windows, "夹具结束后生产窗口被清空")
        self.assertIs(mr._last_report, origin_report, "夹具结束后上报缓存对象未还原")
        self.assertIn("conv-prod", mr._last_report, "夹具结束后上报缓存被清空")


if __name__ == "__main__":
    unittest.main()
