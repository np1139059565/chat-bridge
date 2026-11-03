"""远程桥接 —— 统一推送管线

三条通道的推送流程本质相同，本模块把它固定成一条管线：

    取收件人 → 合并积压 → 取差集 → 检查配额 → 合并/逐条组装 → 发送 → 记账

各通道的差异通过适配器（adapter.py）注入，不再各写一份流程。

三态语义（沿用 QQ 通道既有设计，其余通道同样适用）：
    skip —— 本就不该推（类型开关关闭 / 自己发的 / 内容为空）：记入已推集合
    sent —— 推送成功：记入已推集合
    fail —— 尝试推送但失败（窗口关闭 / 网络错误）：不记账，留待下轮重试

为什么要区分 fail：若失败也记账，该消息此后会被当作「已推过」跳过，
用户永远收不到——表现为「AI 回了但我这边没动静，重启才恢复」。

可插拔钩子（适配器可选实现，用于保留通道专属逻辑）：
    resolve_target(payload)   决定收件人
    merge_batch(items, push)  合并成一条正文（微信配额紧张时用）
    prepare_items(conv, items) 批次预处理（QQ 用来合并上次推送失败的积压）
    before_push / after_push  推送前后的锁外工作（QQ 用来预合成 / 补推语音）
"""
import threading
import time

from . import target as target_store


# 单次上报最多处理多少条消息。
# 长时间不开手机后重开，切片可能堆积几百条；只处理最新的一批，
# 更旧的直接跳过——用户要的本就是「最后几条」。
DEFAULT_MAX_PER_REPORT = 20


def _max_per_report():
    """取当前生效的单次上报条数上限；配置不可用时回退常量。

    @returns 条数上限
    """
    try:
        import tool_config
        v = tool_config.get_value("system", "max_push_per_report")
        return int(v) if v else DEFAULT_MAX_PER_REPORT
    except Exception:
        return DEFAULT_MAX_PER_REPORT


class ConvLocks:
    """按会话分锁：同一会话的推送串行，不同会话互不阻塞。

    为什么按会话而不是全局一把：锁内包含网络发送，全局锁会让一个慢会话
    把其它所有会话的推送一起拖住。
    """

    def __init__(self):
        """初始化锁表与保护锁表的锁。"""
        self._locks = {}
        self._guard = threading.Lock()

    def get(self, conv_id):
        """取某会话的锁，不存在则创建。

        @param conv_id 会话标识
        @returns 该会话的锁
        """
        with self._guard:
            lock = self._locks.get(conv_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[conv_id] = lock
            return lock


def run(adapter, payload, push, log):
    """执行一次推送。

    @param adapter 通道适配器（见 adapter.py）
    @param payload 抽屉上报体：{ conversationId, messages: [...], openid }
    @param push    推送开关字典（控制 user / tool / ai 三类是否推送）
    @param log     日志函数，签名 log(*args)
    @returns 本次成功推送的条数
    """
    conv_id = payload.get("conversationId") or "__default__"
    items = payload.get("messages") or []
    # 空切片：无事可做
    if not items:
        return 0

    # 第一步：确定收件人。缺失时不是丢弃，而是留待下次上报（由适配器决定是否积压）
    recipient = _resolve_recipient(adapter, payload, log)
    if not recipient:
        return 0

    # 第二步：批次预处理（通道可选）。QQ 用它合并上次推送失败的消息：
    # 那些消息可能已滚出可见区，不再出现在切片里，只能靠缓存获得重试机会。
    prepared = adapter.prepare_items(conv_id, items) if hasattr(adapter, "prepare_items") else items
    if not prepared:
        return 0

    # 第三步：条数封顶。放在网络调用之前，保证调用次数被硬性限制。
    limit = _max_per_report()
    if len(prepared) > limit:
        prepared = prepared[-limit:]

    # 第四步：锁外预处理（QQ 在此查语音缓存，不做网络合成）
    ctx = {}
    if hasattr(adapter, "before_push"):
        ctx = adapter.before_push(recipient, conv_id, prepared, push) or {}

    # 第五步：锁内推送。同一会话的「读集合 → 推送 → 写回」必须整体串行，
    # 否则并发上报会读到同一份集合，把同一条消息推两遍。
    # 参数打包成字典传入：锁内函数已需 6 项上下文，再加一项会触发参数个数上限。
    args = {
        "adapter": adapter, "recipient": recipient, "conv_id": conv_id,
        "items": prepared, "push": push, "ctx": ctx, "log": log,
    }
    with adapter._conv_locks.get(conv_id):
        sent = _push_locked(args)

    # 第六步：锁外收尾（QQ 在此并发合成剩余语音并补推）
    if hasattr(adapter, "after_push"):
        adapter.after_push(recipient, conv_id, prepared, push, ctx)

    return sent


def _resolve_recipient(adapter, payload, log):
    """确定收件人：适配器优先，回退到「最近跟我说话的人」。

    @param adapter 通道适配器
    @param payload 上报体
    @param log     日志函数
    @returns 收件人标识；无从确定返回空串
    """
    recipient = adapter.resolve_target(payload)
    if recipient:
        return recipient
    # 上报体没带标识：用最近登记的用户兜底（抽屉上报不带通道侧标识）
    fallback = target_store_for(adapter.name).get()
    if not fallback:
        log("无推送目标，跳过本轮（等用户下次发消息后补推）")
        return ""
    return fallback


def target_store_for(name):
    """按通道名取对应的「最近用户」存储。

    @param name 通道名
    @returns TargetStore 实例
    """
    return getattr(target_store, name)


def _push_locked(args):
    """在会话锁内完成去重与推送，返回成功条数。

    参数打包成字典传入：本函数已需 7 项上下文，逐项传参会触发
    仓库「函数参数不超过 6 个」的结构约束。
    @param args 上下文：adapter / recipient / conv_id / items / push / ctx / log
    @returns 成功推送条数
    """
    adapter = args["adapter"]
    recipient = args["recipient"]
    conv_id = args["conv_id"]
    items = args["items"]
    push = args["push"]
    ctx = args["ctx"]
    log = args["log"]
    # 先筛掉本轮不该推的（类型开关关闭 / 自己发的），它们直接记为已推
    candidates = []
    for m in items:
        if not _should_push(adapter, m, push):
            adapter.dedupe.mark(conv_id, m.get("id") or "")
            continue
        candidates.append(m)
    if not candidates:
        return 0

    # 取差集：只要没推过的，并立即占用（并发下不会重复取到同一条）
    fresh = adapter.dedupe.filter_new(conv_id, [m.get("id") or "" for m in candidates])
    fresh_set = set(fresh)
    todo = [m for m in candidates if (m.get("id") or "") in fresh_set]
    if not todo:
        return 0

    # 配额检查：用尽时本轮不推。
    # 这不属于「推送失败」，而是「此刻不能推」——撤销占用，等配额恢复后
    # 下一轮上报自然会重试，消息不会丢。
    if adapter.quota.exhausted(recipient):
        log("[%s] 配额已用尽，本轮跳过 %d 条" % (adapter.name, len(todo)))
        for m in todo:
            adapter.dedupe.forget(conv_id, m.get("id") or "")
        return 0

    # 通道可要求合并（微信），否则逐条推送。
    # 返回 None 表示「不合并」；返回字符串（含空串）表示「走合并」，
    # 空串意味着这批消息全都不该推（如只有用户消息而开关关闭），
    # 此时直接保留已推标记即可，不必再逐条评估。
    merged = adapter.merge_batch(todo, push) if hasattr(adapter, "merge_batch") else None
    if merged is not None:
        if not merged:
            # 无文本内容不等于无内容可推：这一批可能全是图片 / 语音。
            # 直接返回会让媒体被整批丢掉，故仍走一次媒体发送。
            log("合并后无文本，尝试发送媒体 %d 条" % len(todo))
            if not hasattr(adapter, "push_media"):
                return 0
            media_ok = adapter.push_media(recipient, todo, push, ctx)
            # 一条媒体都没发出去：整批挂起，下轮重试。
            # 若只发出去一部分，已发出的无法逐条判定，按成功处理避免重复发。
            if not media_ok:
                for m in todo:
                    adapter.dedupe.forget(conv_id, m.get("id") or "")
                _save_pending(conv_id, todo)
                return 0
            return media_ok
        ok = adapter.send_text(recipient, merged, markdown=True)
        if ok:
            adapter.quota.record(recipient, 1)
            # 带通道名与接收方：广播时既要看哪条通道发了，也要看发给了谁
            log("[%s] 合并推送成功 %d 条 recipient=%s"
                % (adapter.name, len(todo), recipient))
            # 文本送达后再发媒体：图片 / 文件 / 语音无法并入合并文本，
            # 塞进去就变成一段路径文字，用户看不到内容。
            media = adapter.push_media(recipient, todo, push, ctx) if hasattr(adapter, "push_media") else 0
            return len(todo) + media
        # 合并推送失败：撤回占用并挂起整批，留待下轮重试。
        # 挂起是必要的：这批消息可能已滚出可见区，下轮切片里不再出现，
        # 只撤回占用不足以让它们重试。
        for m in todo:
            adapter.dedupe.forget(conv_id, m.get("id") or "")
        _save_pending(conv_id, todo)
        return 0

    # 逐条推送
    sent = 0
    failed = []
    for m in todo:
        mid = m.get("id") or ""
        if hasattr(adapter, "push_one"):
            outcome = adapter.push_one(recipient, conv_id, m, push, ctx)
        else:
            outcome = _default_push_one(adapter, recipient, m, push)
        if outcome == "fail":
            # 失败不记账：撤回占用，下轮上报会重试
            adapter.dedupe.forget(conv_id, mid)
            failed.append(m)
            continue
        sent += 1
        adapter.quota.record(recipient, 1)
    # 回写待推缓存：本轮失败的消息挂起。
    # 必要性：失败的消息若已滚出可见区，下一轮切片里就没有它了，
    # 只靠「撤回占用」无法让它重试，必须有这份缓存兜住。
    _save_pending(conv_id, failed)
    return sent


def _save_pending(conv_id, failed):
    """把本轮推送失败的消息写入待推缓存，供下一轮补推。

    只在失败时才有意义：成功与跳过的消息不该留在缓存里，
    故整体替换而非追加，天然完成「移出已处理项」。

    @param conv_id 会话 id
    @param failed  本轮失败的消息对象列表
    """
    if not conv_id:
        return
    from .. import bridge_store
    try:
        bridge_store.set_pending(conv_id, failed)
    except Exception:
        # 缓存写入失败不能让主流程崩：消息已撤回占用，下轮仍有机会重试
        pass


def _should_push(adapter, m, push):
    """判断一条消息是否应当推送：类型开关打开，且不是本通道自己发来的。

    @param adapter 通道适配器
    @param m       消息对象
    @param push    推送开关
    @returns 该推返回 True
    """
    from ..message_parse import _classify
    kind = _classify(m)
    # 三类（user / tool / ai）各自控制是否推送
    if not push.get(kind, True):
        return False
    # 通道自己发来的消息不回推，避免复读用户刚说的话
    if hasattr(adapter, "is_own_source"):
        return not adapter.is_own_source(m)
    return True


def _default_push_one(adapter, recipient, m, push):
    """默认的单条推送：组装正文 → 发送 → 返回结果三态。

    通道未覆盖 push_one 时走这里，覆盖后仍可复用它完成基础发送。
    @param adapter   通道适配器
    @param recipient 收件人
    @param m         消息对象
    @param push      推送开关
    @returns 'skip' / 'sent' / 'fail'
    """
    from ..outbound import build_body
    from ..message_parse import _classify
    built = build_body(m, push)
    if built.get("skip"):
        return "skip"
    kind = built.get("kind") or _classify(m)
    text = built.get("text") or ""
    body = "%s\n%s" % (adapter.prefix(kind) if hasattr(adapter, "prefix") else kind, text)
    ok = adapter.send_text(recipient, body, markdown=bool(built.get("markdown")))
    return "sent" if ok else "fail"
