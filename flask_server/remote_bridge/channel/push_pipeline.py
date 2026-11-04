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

    # 第一步：筛出本轮真正要推的消息（去重 + 类型开关 + 来源过滤）
    todo = _fresh_candidates(adapter, conv_id, items, push)
    if not todo:
        return 0

    # 第二步：配额检查。用尽时撤销占用，等配额恢复后下一轮自然重试
    if adapter.quota.exhausted(recipient):
        log("[%s] 配额已用尽，本轮跳过 %d 条" % (adapter.name, len(todo)))
        _revoke_all(adapter, conv_id, todo)
        return 0

    # 第三步：通道若要求合并（微信），走合并分支；否则逐条推送
    merged = adapter.merge_batch(todo, push) if hasattr(adapter, "merge_batch") else None
    if merged is not None:
        # 打包上下文：合并分支需七项上下文，逐项传参会超过参数个数上限
        merged_args = dict(args)
        merged_args["todo"] = todo
        return _push_merged(merged_args, merged)
    return _push_each(adapter, recipient, conv_id, todo, push, ctx)


def _fresh_candidates(adapter, conv_id, items, push):
    """筛出本轮该推且尚未推过的消息，并占用它们的 id。

    两道筛：先按类型开关与来源过滤去掉不该推的（直接记为已推，
    之后不再重复评估），再取差集去掉推过的。

    @returns 待推消息列表；无则空列表
    """
    candidates = []
    for m in items:
        if not _should_push(adapter, m, push):
            # 不该推的也记为已推：避免每轮都重新评估一遍
            adapter.dedupe.mark(conv_id, m.get("id") or "")
            continue
        candidates.append(m)
    if not candidates:
        return []
    # 取差集并立即占用：并发下不会重复取到同一条
    fresh = adapter.dedupe.filter_new(conv_id, [m.get("id") or "" for m in candidates])
    fresh_set = set(fresh)
    return [m for m in candidates if (m.get("id") or "") in fresh_set]


def _revoke_all(adapter, conv_id, items):
    """撤回一批消息的已推占用，使它们下一轮还能重试。

    @param adapter 通道适配器
    @param conv_id 会话标识
    @param items   要撤回的消息列表
    """
    for m in items:
        adapter.dedupe.forget(conv_id, m.get("id") or "")


def _push_merged(ctx_args, merged):
    """合并推送分支：把整批消息作为一条长文本发出。

    参数打包成字典传入，与 _push_locked 同一约定：本分支需 adapter /
    recipient / conv_id / todo / push / ctx / log 七项上下文，逐项传参会
    触发仓库「函数参数不超过 6 个」的结构约束。

    @param ctx_args 上下文：adapter / recipient / conv_id / todo / push / ctx / log
    @param merged   合并后的文本；空串表示这批没有文本内容，只有媒体
    @returns 成功推送的条数（文本条数 + 媒体件数）
    """
    adapter = ctx_args["adapter"]
    recipient = ctx_args["recipient"]
    conv_id = ctx_args["conv_id"]
    todo = ctx_args["todo"]
    push = ctx_args["push"]
    ctx = ctx_args["ctx"]
    log = ctx_args["log"]
    # 合并结果为空串：这批可能全是图片 / 语音，仍要尝试发媒体
    if not merged:
        log("合并后无文本，尝试发送媒体 %d 条" % len(todo))
        return _push_media_only(adapter, recipient, conv_id, todo, push, ctx)

    ok = adapter.send_text(recipient, merged, markdown=True)
    if not ok:
        # 失败：撤回占用并挂起整批。挂起是必要的——这批消息可能已滚出
        # 可见区，下轮切片里不再出现，只撤回占用不足以让它们重试。
        _revoke_all(adapter, conv_id, todo)
        _save_pending(conv_id, todo)
        return 0

    adapter.quota.record(recipient, 1)
    log("[%s] 合并推送成功 %d 条 recipient=%s" % (adapter.name, len(todo), recipient))
    # 文本送达后再发媒体：媒体无法并入合并文本，塞进去就变成一段路径文字
    media = adapter.push_media(recipient, todo, push, ctx) if hasattr(adapter, "push_media") else 0
    return len(todo) + media


def _push_media_only(adapter, recipient, conv_id, todo, push, ctx):
    """纯媒体批次：没有文本可发，只发媒体。

    @returns 成功发送的媒体件数；一件都没发出时返回 0 并挂起整批
    """
    if not hasattr(adapter, "push_media"):
        return 0
    media_ok = adapter.push_media(recipient, todo, push, ctx)
    # 一件都没发出去：整批挂起，下轮重试。
    # 只发出去一部分时无法逐条判定哪件成了，按成功处理避免重复发。
    if not media_ok:
        _revoke_all(adapter, conv_id, todo)
        _save_pending(conv_id, todo)
        return 0
    return media_ok


def _push_each(adapter, recipient, conv_id, todo, push, ctx):
    """逐条推送分支：一条一条发，失败的留待下轮重试。

    @returns 成功推送的条数
    """
    sent = 0
    failed = []
    for m in todo:
        outcome = _push_one_item(adapter, recipient, conv_id, m, push, ctx)
        if outcome == "fail":
            # 失败不记账：撤回占用，下轮上报会重试
            adapter.dedupe.forget(conv_id, m.get("id") or "")
            failed.append(m)
            continue
        sent += 1
        adapter.quota.record(recipient, 1)
    # 失败的消息写入待推缓存：它们可能已滚出可见区，只靠撤回占用不足以重试
    _save_pending(conv_id, failed)
    return sent


def _push_one_item(adapter, recipient, conv_id, m, push, ctx):
    """推送一条消息：优先用通道自己的实现，没有则走默认组装。

    @returns 'skip' / 'sent' / 'fail'
    """
    if hasattr(adapter, "push_one"):
        return adapter.push_one(recipient, conv_id, m, push, ctx)
    return _default_push_one(adapter, recipient, m, push)


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
