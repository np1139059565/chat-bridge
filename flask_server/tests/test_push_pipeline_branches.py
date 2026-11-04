"""统一推送管线的分支行为测试

为什么需要：
    _push_locked 是三条通道共用的推送核心，承担去重、配额、合并、逐条
    四条分支。它曾是一个 101 行的长函数，拆分时最容易出的事是「某条分支
    的失败处理被漏掉」——而失败处理恰恰是「消息发不出去」这类故障的来源。
    本文件把四条分支各自的成功与失败行为钉死，重构后逐条比对。

覆盖内容：
    - 筛选：类型开关关闭 / 来源过滤的消息直接记为已推，不进入推送
    - 去重：已推过的消息不再推
    - 配额：用尽时撤销占用，不留「假已推」
    - 合并：成功计数含媒体、失败时整批挂起
    - 逐条：失败的消息撤回占用并进入待推缓存

运行：python -m pytest tests/test_push_pipeline_branches.py -q
"""
from remote_bridge.channel import push_pipeline


class FakeDedupe:
    """已推集合的替身：用集合记录，行为与真实实现一致。"""

    def __init__(self):
        """初始化空集合。"""
        self._seen = set()

    def mark(self, conv_id, mid):
        """记为已推。"""
        if mid:
            self._seen.add(mid)

    def forget(self, conv_id, mid):
        """撤回已推标记。"""
        self._seen.discard(mid)

    def filter_new(self, conv_id, ids):
        """返回其中尚未推过的 id，并立即占用。"""
        fresh = [i for i in ids if i and i not in self._seen]
        self._seen.update(fresh)
        return fresh


class FakeQuota:
    """配额替身：可指定是否用尽，并记录消耗。"""

    def __init__(self, exhausted=False):
        """@param exhausted 是否已用尽"""
        self._exhausted = exhausted
        self.recorded = 0

    def exhausted(self, recipient):
        """配额是否用尽。"""
        return self._exhausted

    def record(self, recipient, count=1):
        """记一次消耗。"""
        self.recorded += count


class FakeAdapter:
    """适配器替身：行为由构造参数决定。"""

    name = "fake"

    def __init__(self, merged=None, send_ok=True, push_outcome="sent",
                 exhausted=False, own_source=False):
        """按需配置各分支的返回值。"""
        self.dedupe = FakeDedupe()
        self.quota = FakeQuota(exhausted)
        self._merged = merged
        self._send_ok = send_ok
        self._push_outcome = push_outcome
        self._own = own_source
        self.sent_texts = []
        self.media_calls = 0

    def resolve_target(self, payload):
        """固定返回一个收件人。"""
        return "target-1"

    def merge_batch(self, items, push):
        """返回构造时指定的合并结果。"""
        return self._merged

    def send_text(self, target, text, markdown=False):
        """记录发送内容并按配置报告结果。"""
        self.sent_texts.append(text)
        return self._send_ok

    def push_one(self, recipient, conv_id, m, push, ctx):
        """按配置返回三态。"""
        return self._push_outcome

    def is_own_source(self, m):
        """是否本通道自己发来的。"""
        return self._own

    def push_media(self, recipient, items, push, ctx):
        """记录一次媒体推送，返回成功件数。"""
        self.media_calls += 1
        return len(items)


class TestFiltering:
    """筛选与去重分支。"""

    def test_type_switch_off_marks_as_pushed(self, monkeypatch):
        """类型开关关闭的消息直接记为已推，不进入推送。"""
        adapter = FakeAdapter(merged=None)
        # 关掉 user 类
        args = {"adapter": adapter, "recipient": "t", "conv_id": "c",
                "items": [{"id": "m1", "role": "user", "blocks": []}],
                "push": {"user": False}, "ctx": {}, "log": lambda *a: None}
        # 让分类函数恒为 user，专注于开关逻辑
        monkeypatch.setattr(push_pipeline, "_should_push", lambda a, m, p: False)
        assert push_pipeline._push_locked(args) == 0
        # 已被占用：下轮不会再评估
        assert adapter.dedupe.filter_new("c", ["m1"]) == []

    def test_already_pushed_not_sent_again(self):
        """已推过的消息不再推第二次。"""
        adapter = FakeAdapter(merged=None)
        adapter.dedupe.mark("c", "m1")
        args = {"adapter": adapter, "recipient": "t", "conv_id": "c",
                "items": [{"id": "m1", "role": "ai", "blocks": []}],
                "push": {}, "ctx": {}, "log": lambda *a: None}
        assert push_pipeline._push_locked(args) == 0
        assert adapter.sent_texts == []


class TestQuotaBranch:
    """配额用尽分支。"""

    def test_exhausted_revokes_claim(self):
        """配额用尽时撤销占用，消息下一轮还能重试。"""
        adapter = FakeAdapter(exhausted=True)
        args = {"adapter": adapter, "recipient": "t", "conv_id": "c",
                "items": [{"id": "m1", "role": "ai", "blocks": []}],
                "push": {}, "ctx": {}, "log": lambda *a: None}
        assert push_pipeline._push_locked(args) == 0
        # 关键：占用被撤回，而不是被误记为「已推」
        assert adapter.dedupe.filter_new("c", ["m1"]) == ["m1"]


class TestMergedBranch:
    """合并推送分支。"""

    def test_merged_success_counts_media(self):
        """合并成功时，计数含文本条数与媒体条数。"""
        adapter = FakeAdapter(merged="合并后的文本")
        args = {"adapter": adapter, "recipient": "t", "conv_id": "c",
                "items": [{"id": "m1"}, {"id": "m2"}],
                "push": {}, "ctx": {}, "log": lambda *a: None}
        n = push_pipeline._push_locked(args)
        # 文本 2 条 + 媒体 2 件
        assert n == 4
        assert adapter.sent_texts == ["合并后的文本"]

    def test_merged_failure_suspends_batch(self, monkeypatch):
        """合并失败时整批挂起，且撤回占用。"""
        adapter = FakeAdapter(merged="文本", send_ok=False)
        saved = []
        monkeypatch.setattr(push_pipeline, "_save_pending", lambda c, items: saved.extend(items))
        args = {"adapter": adapter, "recipient": "t", "conv_id": "c",
                "items": [{"id": "m1"}], "push": {}, "ctx": {}, "log": lambda *a: None}
        assert push_pipeline._push_locked(args) == 0
        # 进了待推缓存，下轮能重试
        assert [m["id"] for m in saved] == ["m1"]
        # 占用已撤回
        assert adapter.dedupe.filter_new("c", ["m1"]) == ["m1"]

    def test_merged_empty_sends_media_only(self):
        """合并结果为空串（纯媒体批次）时，仍走媒体发送。"""
        adapter = FakeAdapter(merged="")
        args = {"adapter": adapter, "recipient": "t", "conv_id": "c",
                "items": [{"id": "m1"}], "push": {}, "ctx": {}, "log": lambda *a: None}
        assert push_pipeline._push_locked(args) == 1
        assert adapter.media_calls == 1


class TestOneByOneBranch:
    """逐条推送分支。"""

    def test_all_sent(self):
        """逐条全部成功时计数正确。"""
        adapter = FakeAdapter(merged=None, push_outcome="sent")
        args = {"adapter": adapter, "recipient": "t", "conv_id": "c",
                "items": [{"id": "m1"}, {"id": "m2"}],
                "push": {}, "ctx": {}, "log": lambda *a: None}
        assert push_pipeline._push_locked(args) == 2

    def test_failed_goes_to_pending(self, monkeypatch):
        """逐条失败的消息进入待推缓存并撤回占用。"""
        adapter = FakeAdapter(merged=None, push_outcome="fail")
        saved = []
        monkeypatch.setattr(push_pipeline, "_save_pending", lambda c, items: saved.extend(items))
        args = {"adapter": adapter, "recipient": "t", "conv_id": "c",
                "items": [{"id": "m1"}], "push": {}, "ctx": {}, "log": lambda *a: None}
        assert push_pipeline._push_locked(args) == 0
        assert [m["id"] for m in saved] == ["m1"]
        # 占用撤回，下轮可重试
        assert adapter.dedupe.filter_new("c", ["m1"]) == ["m1"]
