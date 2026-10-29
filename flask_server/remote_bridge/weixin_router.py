"""远程桥接 —— 微信推送路由

职责：处理抽屉上报，把本轮新增消息合并成一条文本发回微信。

与 QQ 推送（message_router.handle_report）的根本差异：
  QQ：一条消息推一条，配额宽松。
  微信：24 小时内最多 10 条独立消息，且不支持主动推送。
        若照搬逐条推送，一轮「用户问 + 工具调用 + AI 答」就吃掉 3 条，
        三轮对话即耗尽配额。故此处必须把整批消息合并为一条长文本。

去重命名空间：
  微信使用独立会话键（conv_id + 后缀），与 QQ 的已推集合互不干扰。
  两者同时开启时，同一条消息各自都能推到自己的平台。

消息来源过滤：
  不回推微信自己发来的话（source == 'weixin'），避免复读用户刚说的内容。
"""
import threading
import time

from . import bridge_store, bridge_log
from .message_parse import _classify, _blocks_to_text, _has_qq_source


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][weixin]", *args)


# 微信会话键后缀：与 QQ 的已推集合隔离，避免互相压制。
CONV_SUFFIX = "@wx"
# 单条消息最多发送的字符数。
# 微信对文本长度有上限，且过长的消息在手机上体验很差；
# 超长时保留开头与结尾，中间用省略标记，保证关键信息可见。
MAX_TEXT_CHARS = 1800
# 合并多条消息时的分隔线。
SEP = "\n\n———\n\n"
# 各类消息的展示前缀，与 QQ 保持一致的视觉语言。
PREFIX = {"user": "👤 用户", "tool": "🛠 工具", "ai": "🤖 AI"}

# 推送串行锁：同一会话的「读已推集合 → 发送 → 写回」必须整体串行，
# 否则并发上报会重复发送，白白消耗本已紧张的配额。
#
# 必须用可重入锁：handle_report 持锁期间会调用 _quota_used，
# 后者自身也要取同一把锁。用普通 Lock 会在此自锁死——
# 表现为上报请求永久挂起、日志无任何输出。
_lock = threading.RLock()

# 最近一次发来消息的用户：抽屉上报时并不带微信侧的用户标识，
# 推送目标靠它兜底（与 QQ 的 _last_openid 同一思路）。
_last_user = ""


# 已发送条数记账：{ 用户id: [(时间戳, 条数), ...] }
# 用于在配额将满时给出明确提示，而不是让用户面对「发了但对方收不到」。
_quota = {}
# 24 小时窗口（秒）与条数上限。
QUOTA_WINDOW = 24 * 60 * 60
QUOTA_LIMIT = 10


def note_incoming(user_id):
    """记录最近发来消息的用户，供推送目标兜底，并持久化。

    为什么要持久化：抽屉上报时并不带微信侧的用户标识，推送目标靠它兜底。
    若只存内存，服务重启后该值为空，此后的上报会因「找不到推送目标」
    而静默失败——表现为「AI 回了但微信收不到，重启才恢复」。
    落盘后重启即可恢复，直到用户下次发消息刷新。

    @param user_id 用户标识
    """
    global _last_user
    if not user_id:
        return
    _last_user = user_id
    # 关键：用户发来新消息即重置回复池。
    # 微信的额度是「每条用户消息发放一个约 10 条的池子」，
    # 不重置的话，持续对话会在第 10 轮被自己拦住，与平台实际行为不符。
    _quota_reset(user_id)
    try:
        bridge_store.save_last_weixin_user(user_id)
    except Exception as e:
        log("持久化推送目标失败（不影响本次推送）：", e)


def last_user():
    """取最近发来消息的用户标识；内存为空时从磁盘恢复。

    惰性恢复而非模块导入时恢复：导入发生在服务启动早期，
    此时配置层可能尚未就绪，读盘会引入不必要的启动顺序依赖。
    @returns 用户标识；无从确定时为空串
    """
    global _last_user
    if _last_user:
        return _last_user
    try:
        _last_user = bridge_store.load_last_weixin_user() or ""
    except Exception as e:
        log("恢复推送目标失败：", e)
        _last_user = ""
    return _last_user


def _quota_slot(user_id):
    """取某用户当前的回复池；不存在或已过期则返回 None。

    回复池的真实机制：用户每发一条消息，服务端就发放一个「约 10 条」的回复池，
    有效期到该消息后 24 小时。用户再发消息会刷新并重置这个池子。
    因此计数必须「按用户消息重置」，而不是「按时间窗口累计」——
    后者会让持续对话在第 10 轮被自己拦住，而微信实际允许每轮回 10 条。

    @param user_id 用户标识
    @returns {used, started} 或 None
    """
    now = time.time()
    with _lock:
        slot = _quota.get(user_id)
        if not slot:
            return None
        # 超过 24 小时未再收到该用户消息：池子失效，清理掉
        if now - slot.get("started", 0) >= QUOTA_WINDOW:
            _quota.pop(user_id, None)
            return None
        return dict(slot)


def _quota_reset(user_id):
    """用户发来新消息：重置其回复池。

    这是与真实机制对齐的关键一步：每收到一条用户消息，
    回复额度就重新计算，而不是在旧计数上继续累加。
    @param user_id 用户标识
    """
    with _lock:
        _quota[user_id] = {"used": 0, "started": time.time()}


def _quota_used(user_id):
    """统计某用户当前回复池已用条数。

    @param user_id 用户标识
    @returns 已用条数；无有效池子返回 0
    """
    slot = _quota_slot(user_id)
    return slot.get("used", 0) if slot else 0


def _quota_add(user_id, count=1):
    """记一次发送，累加当前回复池的使用量。

    池子不存在时先建一个：单用户场景下，用户发消息与推送之间可能存在
    极短的时间差，此时以「此刻」为起点建池，避免发送被误拦。
    @param user_id 用户标识
    @param count   本次占用的条数
    """
    with _lock:
        slot = _quota.get(user_id)
        if not slot or time.time() - slot.get("started", 0) >= QUOTA_WINDOW:
            slot = {"used": 0, "started": time.time()}
            _quota[user_id] = slot
        slot["used"] = slot.get("used", 0) + count


def quota_status(user_id):
    """返回某用户的回复池状态，供设置页展示。

    @param user_id 用户标识
    @returns {used, limit, remaining, active}
        active 表示当前是否有有效回复池（无池子意味着用户还没发过消息）
    """
    slot = _quota_slot(user_id)
    used = slot.get("used", 0) if slot else 0
    return {"used": used, "limit": QUOTA_LIMIT,
            "remaining": max(0, QUOTA_LIMIT - used),
            "active": bool(slot)}


def _is_pure_tool_call(m):
    """判断一条消息是否只含工具调用、没有可读正文。

    为什么需要：AI 干活的中间过程（调用工具、贴代码参数）对用户是噪音，
    在微信上尤其糟——配额本就紧张，还被 JSON 占满。
    但只跳过「纯工具调用」的消息：若同一消息里还有正文（如「我查一下」），
    正文仍要推给用户，不能整条丢弃。

    @param m 消息对象
    @returns 纯工具调用返回 True
    """
    from .message_parse import _block_text_of, _load_json_block
    has_tool = False
    for b in (m.get("blocks") or []):
        if not b:
            continue
        btype = b.get("type")
        # 思考块不算正文：AI 的内部推理不该让它「看起来有内容」
        if btype == "thinking":
            continue
        if btype == "code":
            obj = _load_json_block(b)
            if obj and obj.get("type") == "bridge-chat-call":
                has_tool = True
                continue
        # 任何带文字的其它块都说明有真实内容
        if _block_text_of(b).strip():
            return False
    return has_tool


def _should_push(m, push):
    """判断一条消息是否应当推送到微信。

    规则：类型开关打开、不是微信自己发来的、且不是纯工具调用。
    @param m    消息对象
    @param push 推送开关字典
    @returns 需要推送返回 True
    """
    kind = _classify(m)
    if not push.get(kind, True):
        return False
    # 来源过滤：微信自己投出去的卡片不回推，否则会把用户刚说的话复读一遍
    if _is_from_weixin(m):
        return False
    # 纯工具调用不推：内部工作过程对用户是噪音，且会挤占微信紧张的配额。
    # 带正文的消息不受影响，正文照常推送。
    if _is_pure_tool_call(m):
        return False
    return True


def _is_from_weixin(m):
    """判断消息是否来自微信（由本桥接层投递的外部卡片）。

    与 message_parse._has_qq_source 同构，但判的是微信来源标记。
    @param m 消息对象
    @returns 来自微信返回 True
    """
    from .message_parse import _parse_envelope
    obj = _parse_envelope(m)
    return bool(obj and obj.get("source") == "weixin")


def _extract_weixin_text(m, push):
    """提取给微信看的正文：只保留自然语言，剔除工具调用代码。

    为什么不能复用 QQ 的 build_body：
      QQ 把工具调用渲染成「[工具调用] run_command 参数={...}」，
      参数里的代码会整段进入正文。这对 QQ 是「看得见 AI 在干活」，
      对微信却是灾难：手机上一屏全是 JSON，且挤占本就紧张的配额。

    微信的取舍是「只推结果，不推过程」：
      保留 —— 段落、标题、列表、表格、引用（用户要读的内容）
      剔除 —— 工具调用块、工具结果块、语音块（AI 的内部工作痕迹）
      保留普通代码块（用户可能确实需要看代码）

    @param m    消息对象
    @param push 推送开关字典
    @returns 正文文本；无可用内容返回空串
    """
    from .message_parse import _BLOCK_HANDLERS, _load_json_block
    parts = []
    for b in (m.get("blocks") or []):
        if not b:
            continue
        btype = b.get("type")
        # 代码块需辨认：是工具调用/结果就丢，是真正的代码就留
        if btype == "code":
            obj = _load_json_block(b)
            if obj and obj.get("type") in ("bridge-chat-call", "bridge-chat-res", "bridge-voice"):
                continue
            code = str(b.get("code") or "").strip()
            if code:
                parts.append("```\n" + code + "\n```")
            continue
        # 其余块按既有处理器转文本（思考受开关控制）
        fn = _BLOCK_HANDLERS.get(btype)
        if not fn:
            continue
        text = fn(b, bool(push.get("thinking")))
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _body_of(m, push):
    """取一条消息要推送的正文，带类型前缀。

    @param m    消息对象
    @param push 推送开关字典
    @returns 正文；无需推送返回空串
    """
    if not _should_push(m, push):
        return ""
    text = _extract_weixin_text(m, push)
    if not text:
        return ""
    kind = _classify(m)
    return "%s\n%s" % (PREFIX.get(kind, kind), text)


def _truncate(text):
    """按上限截断文本，保留首尾。

    超长时保留开头与结尾：开头通常是结论，结尾通常是收尾说明，
    中间的技术细节对手机阅读的价值相对低。
    @param text 原文本
    @returns 截断后的文本
    """
    if len(text) <= MAX_TEXT_CHARS:
        return text
    head = MAX_TEXT_CHARS * 2 // 3
    tail = MAX_TEXT_CHARS - head - 20
    return text[:head] + "\n\n…（中间省略）…\n\n" + text[-tail:]


def _is_weixin_id(uid):
    """判断标识是否属于微信用户（iLink 下发的形如 xxx@im.wechat）。

    @param uid 用户标识
    @returns 属于微信返回 True
    """
    return bool(uid) and str(uid).endswith("@im.wechat")


def _resolve_user(payload):
    """确定推送目标：只接受微信标识，否则回退到最近发来消息的微信用户。

    为什么不能照单全收 payload.openid：抽屉上报时该字段装的是 QQ 桥接
    写入的 QQ openid（或网页固定标识）。拿 QQ 的 id 去调微信发送接口，
    服务端会直接返回 -3 invalid arguments，消息一条也发不出去。

    优先级：上报体显式带的微信标识 > 上报体里恰好是微信格式的 openid
            > 最近一个真正发来微信消息的用户。

    @param payload 上报体
    @returns 微信用户标识；无从确定时为空串
    """
    explicit = payload.get("weixin_user") or ""
    if _is_weixin_id(explicit):
        return explicit
    raw = payload.get("openid") or ""
    if _is_weixin_id(raw):
        return raw
    # payload 里的 QQ / 网页标识一律丢弃，回退到微信自己的记账
    return last_user()


def _collect_fresh(conv_id, messages):
    """从上报切片里筛出「尚未推送过」的消息。

    抽屉每次上报全量可见切片，故必须与已推集合取差集；
    无 id 的消息无法记账，一律跳过。
    @param conv_id  会话键（已含微信后缀）
    @param messages 上报的消息列表
    @returns 新消息列表
    """
    pushed = bridge_store.get_pushed_set(conv_id)
    return [m for m in messages if (m.get("id") or "") and m.get("id") not in pushed]


def _collect_bodies(fresh, push):
    """把新消息逐条转成待发正文，过滤掉不该推的。

    @param fresh 新消息列表
    @param push  推送开关
    @returns 正文列表（可能为空）
    """
    return [b for b in (_body_of(m, push) for m in fresh) if b]


def _mark_all(conv_id, fresh):
    """把一批消息记为已推送。

    @param conv_id 会话键
    @param fresh   消息列表
    """
    bridge_store.mark_pushed(conv_id, [m.get("id") for m in fresh])


def _send_merged(client, user_id, conv_id, fresh, bodies):
    """把合并后的正文发出去，并按结果记账。

    成功才记入已推集合并累加配额；失败不记账，留给下轮上报重试，
    否则消息会被永久漏掉。
    @param client  WeixinClient 实例
    @param user_id 接收方
    @param conv_id 会话键
    @param fresh   本轮新消息（用于记账）
    @param bodies  正文列表
    @returns 发送成功返回 1，失败返回 0
    """
    text = _truncate(SEP.join(bodies))
    ok, data = client.send_text(user_id, text)
    if not ok:
        log("发送失败（下轮重试）：", str(data)[:200])
        return 0
    _quota_add(user_id, 1)
    _mark_all(conv_id, fresh)
    log("已合并发送 %d 条消息，长度 %d" % (len(bodies), len(text)))
    return 1


def handle_report(client, payload):
    """处理抽屉上报：差集出新消息，合并成一条发回微信。

    合并而非逐条，是配额约束下的硬要求：微信每条用户消息只发一个
    约 10 条的回复池，逐条推会迅速耗尽。

    @param client  WeixinClient 实例
    @param payload 上报体 {conversationId, messages:[{id, role, blocks}], weixin_user}
    @returns 本次发送的消息条数（0 或 1）
    """
    if not client:
        return 0
    conv_id = (payload.get("conversationId") or "__default__") + CONV_SUFFIX
    user_id = _resolve_user(payload)
    messages = payload.get("messages") or []
    if not user_id or not messages:
        return 0
    push = bridge_store.get_config().get("push") or {}
    # 串行：同一会话的「读集合 → 发送 → 写回」必须整体原子，避免重复发送
    with _lock:
        fresh = _collect_fresh(conv_id, messages)
        if not fresh:
            return 0
        bodies = _collect_bodies(fresh, push)
        # 全部消息都不该推（如只开了 AI 开关、本轮只有用户消息）：
        # 仍要记账，避免下次上报反复评估同一批消息。
        if not bodies:
            _mark_all(conv_id, fresh)
            return 0
        if _quota_used(user_id) >= QUOTA_LIMIT:
            # 回复池已满：平台硬限制，等用户下一条消息重置
            log("本轮回复池已满（%d 条），等用户新消息重置 user=%s"
                % (QUOTA_LIMIT, user_id[:8]))
            return 0
        return _send_merged(client, user_id, conv_id, fresh, bodies)
