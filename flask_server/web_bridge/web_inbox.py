"""网页版机器人 —— 对话收件箱（存储层）

职责：
1. 把网页版对话的消息按顺序落盘，供手机网页主动拉取
2. 提供「游标增量拉取」：调用方带着上次拿到的 seq 来，只取之后的新消息
3. 维护消息数量上限，超出时丢弃最旧的，避免文件无限增长

设计说明：
- 网页版与 QQ 共用同一场对话（用户拍板 1A），但两者的「推送方式」不同：
  QQ 走被动回复窗口主动推；网页版走「打开页面后主动拉」。
  因此本模块只负责「存」，拉取策略由路由层决定。
- 游标用单调递增的 seq（整数），比时间戳可靠：同一毫秒内多条消息也不会乱序。
- 所有写操作加锁：消息可能从抽屉上报线程与网页请求线程同时写入。
"""
import json
import threading
import time

import paths

# 消息数量上限：超出后丢弃最旧的，防止收件箱文件无限膨胀。
# 手机端只需看最近内容，历史靠 QQ 侧与抽屉存档，无需在此长期留存。
MAX_MESSAGES = 500

# 用可重入锁：读改写同一份文件，需整体串行。
_lock = threading.RLock()

# 内存缓存：收件箱每次读取都要解析整个 JSON，而网页每 2.5 秒轮询一次，
# 镜像又要对切片逐条调用 is_seen。若每次都全量读盘解析，开销随消息量持续放大。
# 这里缓存「状态对象 + 文件签名（mtime 纳秒 + 大小）」：签名未变直接复用，
# 外部改动（如手工编辑）也能被签名变化感知、自动重读。
_cache = None
_cache_sig = None


def _file_sig():
    """取收件箱文件的签名（mtime 纳秒 + 大小）；文件不存在返回 None。"""
    try:
        st = paths.WEB_INBOX_PATH.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _empty_state():
    """收件箱的初始状态：空消息列表 + 游标归零 + 已入库源 id 集合。

    seen 用于按「源消息 id」去重：抽屉每次上报的是全量可见切片，
    若不去重，同一轮对话会被反复写进收件箱。
    """
    return {"seq": 0, "messages": [], "seen": []}


def _read_state():
    """读取收件箱状态（带缓存）。不存在或损坏时返回空结构。

    损坏时不抛异常：收件箱是「尽力而为」的展示缓存，
    宁可当作空箱重新开始，也不能让网页版整个不可用。
    缓存策略：比对文件签名，未变则直接返回内存对象，避免重复解析大 JSON。
    """
    global _cache, _cache_sig
    path = paths.WEB_INBOX_PATH
    sig = _file_sig()
    if _cache is not None and sig is not None and sig == _cache_sig:
        return _cache
    if not path.exists():
        _cache = _empty_state()
        _cache_sig = None
        return _cache
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print("[web] 读取收件箱失败，按空箱处理：", e)
        _cache = _empty_state()
        _cache_sig = sig
        return _cache
    # 字段兜底：外部改坏文件时不至于让后续逻辑崩在 None 上
    if not isinstance(data, dict):
        _cache = _empty_state()
        _cache_sig = sig
        return _cache
    msgs = data.get("messages")
    if not isinstance(msgs, list):
        msgs = []
    seq = data.get("seq")
    if not isinstance(seq, int):
        seq = 0
    seen = data.get("seen")
    if not isinstance(seen, list):
        seen = []
    _cache = {"seq": seq, "messages": msgs, "seen": seen}
    _cache_sig = sig
    return _cache


def _write_state(state):
    """把收件箱状态写回磁盘，并同步刷新内存缓存。

    先确保目录存在；写失败只记录——收件箱是缓存，写不进去不应阻断消息流。
    写成功后立即更新 _cache 与签名，使后续读取不必再解析一遍。
    """
    global _cache, _cache_sig
    path = paths.WEB_INBOX_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print("[web] 写回收件箱失败：", e)
        return
    _cache = state
    _cache_sig = _file_sig()


def _norm_image(image):
    """归一化图片字段：支持单张（字符串）与多张（列表）。

    单张存字符串（兼容旧数据与只认字符串的读取方）；多张存字符串列表。
    空值一律存空串，前端据此判断「有无图片」。
    @param image 字符串或字符串列表
    @returns 字符串或字符串列表
    """
    if isinstance(image, (list, tuple)):
        names = [str(x) for x in image if x]
        return names
    return str(image or "")


def append(role, text, voice="", kind="", image=""):
    """向收件箱追加一条消息，返回该消息对象。

    @param role  角色：user（网页/QQ 用户）/ ai（AI 回复）/ tool / system
    @param text  正文（网页端直接展示的文本，AI 消息为 Markdown 原文）
    @param voice 可选，语音文件名（相对音频目录），网页据此自动播放
    @param kind  可选，附加类型标记（如 command-image），供前端区分展示
    @param image 可选，图片文件名（相对网页图片目录），前端据此渲染 <img>
    @returns 追加后的消息对象（含分配好的 seq 与 id）
    """
    with _lock:
        state = _read_state()
        # 游标自增：seq 从 1 开始，作为拉取增量与消息 id 的双重依据
        state["seq"] = int(state.get("seq") or 0) + 1
        seq = state["seq"]
        msg = {
            "seq": seq,
            "id": "w-" + str(seq),
            "role": role or "user",
            "text": str(text or ""),
            "voice": str(voice or ""),
            "image": _norm_image(image),
            "kind": str(kind or ""),
            "ts": int(time.time() * 1000),
        }
        messages = state.get("messages") or []
        messages.append(msg)
        # 超上限则截断最旧的：保留末尾 MAX_MESSAGES 条
        if len(messages) > MAX_MESSAGES:
            messages = messages[-MAX_MESSAGES:]
        state["messages"] = messages
        _write_state(state)
        return msg


def append_many(items):
    """批量入库并去重，返回真正新增的消息列表。

    抽屉上报的是全量切片，同一条消息会被反复上报；本函数按每条 item 的
    source_id（抽屉里的消息 id）去重，只有首次出现才写进收件箱。
    整个批次共用一次读改写，避免逐条写盘。
    @param items 列表，每项 {source_id, role, text, voice, kind}
    @returns 新增的消息对象列表（按入库顺序）
    """
    added = []
    with _lock:
        state = _read_state()
        seen = set(state.get("seen") or [])
        messages = state.get("messages") or []
        seq = int(state.get("seq") or 0)
        changed = False
        # 内容级判重集合：仅对 ai / tool 两类生效。
        # 原因：抽屉按「基于 blocks 的指纹」去重，而镜像正文优先用 md；
        # AI 流式生成时 blocks 会增长、指纹随之变化，但 md 最终稳定，
        # 导致同一条消息因指纹漂移被当成新消息、重复入库。
        # user 不纳入：用户可能连发两条相同的话，需保留。
        # system 不纳入：指令回执（如两次 /help）内容可能完全相同，
        #   但那是两次真实执行，都该显示，不能被判重吞掉。
        content_seen = set()
        for m in messages:
            r = m.get("role")
            if r in ("ai", "tool"):
                content_seen.add((r, m.get("text") or ""))
        for it in (items or []):
            sid = str(it.get("source_id") or "")
            # 无源 id 的条目（如网页自己发的）允许直接入库，不去重
            if sid and sid in seen:
                continue
            # 内容级判重：同类消息正文完全相同时跳过，兜住指纹漂移导致的重复。
            # 注意 content_seen 必须随新增同步累加，否则同一批内的重复条目会漏判。
            _role = it.get("role") or "user"
            _text = str(it.get("text") or "")
            if _role in ("ai", "tool", "system") and (_role, _text) in content_seen:
                continue
            seq += 1
            msg = {
                "seq": seq,
                "id": "w-" + str(seq),
                "role": it.get("role") or "user",
                "text": str(it.get("text") or ""),
                "voice": str(it.get("voice") or ""),
                "image": _norm_image(it.get("image")),
                "kind": str(it.get("kind") or ""),
                "ts": int(it.get("ts") or (time.time() * 1000)),
            }
            messages.append(msg)
            added.append(msg)
            if sid:
                seen.add(sid)
            # 同步累加内容级判重集合：同一批内后续的重复条目据此跳过
            if _role in ("ai", "tool", "system"):
                content_seen.add((_role, _text))
            changed = True
        if not changed:
            return []
        if len(messages) > MAX_MESSAGES:
            messages = messages[-MAX_MESSAGES:]
        state["seq"] = seq
        state["messages"] = messages
        # 已入库源 id 同样限长：只保留与现存消息规模相当的一批，
        # 避免它本身无界增长（它只是一份去重用的索引）。
        state["seen"] = list(seen)[-MAX_MESSAGES * 2:]
        _write_state(state)
    return added


def is_seen(source_id):
    """判断某条源消息是否已入库（用于避免重复做重活，如语音合成）。

    @param source_id 抽屉里的消息 id
    @returns 已入库为 True
    """
    sid = str(source_id or "")
    if not sid:
        return False
    with _lock:
        state = _read_state()
    return sid in set(state.get("seen") or [])


def list_since(cursor=0, limit=200):
    """拉取游标之后的新消息（增量）。

    @param cursor 上次拿到的最大 seq；传 0 表示首次拉取
    @param limit  单次最多返回条数，避免一次拉太多卡住手机
    @returns {seq, messages}：seq 为当前最新游标，messages 为新消息（按时间正序）
    """
    with _lock:
        state = _read_state()
    try:
        cur = int(cursor)
    except (TypeError, ValueError):
        cur = 0
    messages = state.get("messages") or []
    # 只取 seq 严格大于游标的：等于游标说明已拉过，不重复
    fresh = [m for m in messages if int(m.get("seq") or 0) > cur]
    # 超过单次上限时截取最新的一批（末尾 limit 条），保证尽量看到最新内容。
    # 关键：返回给客户端的游标必须是「本批最后一条」的 seq，而非全局最新 seq。
    # 否则中间被截断的消息会因游标一步跳到最后而永久拉不到。
    # 下一轮拉取会从这条之后继续，直到追平全局最新。
    if len(fresh) > limit:
        # 取「最旧的一批」而非最新一批：配合返回本批末条 seq 作游标，
        # 客户端下一轮从此继续，逐批追平，中间消息不会被跳过。
        # （早前取末尾会让中间段永久拉不到，已由自测发现并改正。）
        fresh = fresh[:limit]
    if fresh:
        next_cursor = int(fresh[-1].get("seq") or 0)
    else:
        # 无新消息：游标保持客户端的旧值即可（不推进，也不后退）
        next_cursor = cur
    return {"seq": next_cursor, "messages": fresh}


def recent(limit=50):
    """取最近的若干条消息（首次打开页面时用于铺满一屏历史）。

    @param limit 条数上限
    @returns {seq, messages}：messages 按时间正序
    """
    with _lock:
        state = _read_state()
    messages = state.get("messages") or []
    if limit and len(messages) > limit:
        messages = messages[-limit:]
    return {"seq": int(state.get("seq") or 0), "messages": messages}


def clear():
    """清空收件箱（供调试或用户主动重置）。"""
    with _lock:
        _write_state(_empty_state())
