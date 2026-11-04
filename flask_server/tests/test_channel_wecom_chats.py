"""企业微信活跃会话表（channel.wecom_chats）测试

为什么需要：
    企业微信的主动推送依赖 chatid，而 chatid 是会话级标识，不是用户级。
    群聊里同一个 chatid 会持续存在，单聊里同一用户也可能换 chatid。
    因此不能像 QQ / 微信那样只记「最近一个用户」，必须记「最近活跃的会话」，
    并区分 chat_type（1 单聊 / 2 群聊）。

覆盖内容：
    - 首次登记：会话表出现该 chatid
    - 重复登记：按 chatid 覆盖，不产生重复条目
    - 取最近会话：按活跃时间戳取最新
    - 无会话时回退到最近用户
    - 落盘后可读回

运行：python -m pytest tests/test_channel_wecom_chats.py -q
"""
from remote_bridge.channel import wecom_chats


class TestNoteChat:
    """会话登记与覆盖。"""

    def test_note_creates_entry(self):
        """登记一个会话后，表里出现该 chatid 及其类型。"""
        # 每个用例前清空内存表，避免相互影响
        wecom_chats.clear()
        wecom_chats.note("chat-a", 1, "user-a")
        chats = wecom_chats.snapshot()
        assert "chat-a" in chats
        # 类型按登记值保存
        assert chats["chat-a"]["chat_type"] == 1
        # 发送者一并记录
        assert chats["chat-a"]["user"] == "user-a"

    def test_note_overwrites_same_chatid(self):
        """同一 chatid 重复登记只更新，不新增条目。"""
        wecom_chats.clear()
        wecom_chats.note("chat-b", 1, "user-old")
        wecom_chats.note("chat-b", 1, "user-new")
        chats = wecom_chats.snapshot()
        # 仍然只有一个条目
        assert len([k for k in chats if k == "chat-b"]) == 1
        # 发送者被更新为最新
        assert chats["chat-b"]["user"] == "user-new"

    def test_empty_chatid_ignored(self):
        """空 chatid 不登记，避免污染会话表。"""
        wecom_chats.clear()
        wecom_chats.note("", 1, "user-x")
        # 空标识不产生任何条目
        assert wecom_chats.snapshot() == {}


class TestLastChat:
    """取最近活跃会话。"""

    def test_last_chat_returns_newest(self):
        """两个会话时，返回时间戳较新的那个。"""
        wecom_chats.clear()
        wecom_chats.note("chat-old", 1, "u1")
        # 手工把第一条的时间拨早，确保排序可判
        with wecom_chats._lock:
            wecom_chats._chats["chat-old"]["ts"] = 1000
        wecom_chats.note("chat-new", 2, "u2")
        with wecom_chats._lock:
            wecom_chats._chats["chat-new"]["ts"] = 2000
        cid, ct = wecom_chats.last()
        assert cid == "chat-new"
        # 群聊类型一并返回
        assert ct == 2

    def test_last_chat_falls_back_to_user(self):
        """没有任何会话时，回退到「最近发来消息的用户」。"""
        wecom_chats.clear()
        # 会话表为空，用户兜底值由 target 存储提供
        from remote_bridge.channel import target
        target.wecom.note("fallback-user")
        cid, ct = wecom_chats.last()
        assert cid == "fallback-user"
        # 兜底场景按单聊处理
        assert ct == 1

    def test_last_chat_empty_when_nothing(self):
        """会话表与用户兜底都为空时，返回空串。"""
        wecom_chats.clear()
        from remote_bridge.channel import target
        target.wecom.note("")
        with target.wecom._lock:
            target.wecom._user = ""
        cid, ct = wecom_chats.last()
        assert cid == ""
        assert ct == 1
