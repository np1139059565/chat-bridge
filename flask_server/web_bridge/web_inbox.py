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
from contextlib import contextmanager

import paths
import app_log

# 消息数量上限：超出后丢弃最旧的，防止收件箱文件无限膨胀。
# 手机端只需看最近内容，历史靠 QQ 侧与抽屉存档，无需在此长期留存。
MAX_MESSAGES = 500

# 用可重入锁：读改写同一份文件，需整体串行。
_lock = threading.RLock()

# 慢锁阈值（毫秒）：等锁或持锁超过此值即告警。
# 用途：定位「界面轮询被堵」——手机端 /api/web/messages 与写收件箱共用这把锁，
# 若某次写操作长时间持锁，轮询就会排队等待、表现为「界面卡住」。
# 只在超过阈值时记录，正常毫秒级操作不产生日志，不会刷屏。
_SLOW_LOCK_MS = 100.0


def _note_slow_lock(op, wait_ms, hold_ms):
    """等锁或持锁超阈值时告警，用于定位界面轮询被堵的根因。

    @param op      操作名（list_since / append_many / set_voice）
    @param wait_ms 等待获取锁的毫秒数
    @param hold_ms 持锁执行的毫秒数
    """
    if wait_ms >= _SLOW_LOCK_MS or hold_ms >= _SLOW_LOCK_MS:
        app_log.warn("[web][inbox]",
                     "%s 等锁=%.0fms 持锁=%.0fms" % (op, wait_ms, hold_ms))


@contextmanager
def _timed_lock(op):
    """带耗时监控的锁：记录等锁与持锁耗时，超阈值即告警。

    语义与 `with _lock:` 完全一致，只是多了计时。正常毫秒级操作不产生日志。
    @param op 操作名，用于日志区分
    """
    t0 = time.perf_counter()
    _lock.acquire()
    wait_ms = (time.perf_counter() - t0) * 1000.0
    t1 = time.perf_counter()
    try:
        yield
    finally:
        hold_ms = (time.perf_counter() - t1) * 1000.0
        _lock.release()
        _note_slow_lock(op, wait_ms, hold_ms)

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
        app_log.warn("[web]", "读取收件箱失败，按空箱处理：", e)
        _cache = _empty_state()
        _cache_sig = sig
        return _cache
    # 字段兜底：外部改坏文件时不至于让后续逻辑崩在 None 上
    _cache = _sanitize_state(data)
    _cache_sig = sig
    return _cache


def _sanitize_state(data):
    """把读到的原始数据规整为合法状态（字段类型不对时用兜底值）。

    @param data 从磁盘 JSON 解析出的对象
    @returns {seq, messages, seen} 状态字典
    """
    if not isinstance(data, dict):
        return _empty_state()
    msgs = data.get("messages")
    if not isinstance(msgs, list):
        msgs = []
    seq = data.get("seq")
    if not isinstance(seq, int):
        seq = 0
    seen = data.get("seen")
    if not isinstance(seen, list):
        seen = []
    return {"seq": seq, "messages": msgs, "seen": seen}


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
        app_log.warn("[web]", "写回收件箱失败：", e)
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


def append(role, text, voice="", kind="", image="", voice_text=""):
    """向收件箱追加一条消息，返回该消息对象。

    @param role  角色：user（网页/QQ 用户）/ ai（AI 回复）/ tool / system
    @param text  正文（网页端直接展示的文本，AI 消息为 Markdown 原文）
    @param voice 可选，已合成的语音文件名（相对音频目录）；为空表示尚未合成
    @param kind  可选，附加类型标记（如 command-image），供前端区分展示
    @param image 可选，图片文件名（相对网页图片目录），前端据此渲染 <img>
    @param voice_text 可选，待朗读的文本；点播时据此按需合成，不占用上报链路
    @returns 追加后的消息对象（含分配好的 seq 与 id）
    """
    # 复用 _make_msg 构造消息对象，避免与 append_many 各写一份字段表
    it = {
        "role": role, "text": text, "voice": voice, "voice_text": voice_text,
        "image": image, "kind": kind, "key": "", "ts": None,
    }
    with _timed_lock('append'):
        state = _read_state()
        # 游标自增：seq 从 1 开始，作为拉取增量与消息 id 的双重依据
        state["seq"] = int(state.get("seq") or 0) + 1
        msg = _make_msg(it, state["seq"])
        messages = state.get("messages") or []
        messages.append(msg)
        # 超上限则截断最旧的：保留末尾 MAX_MESSAGES 条
        if len(messages) > MAX_MESSAGES:
            messages = messages[-MAX_MESSAGES:]
        state["messages"] = messages
        _write_state(state)
        return msg


def _content_seen_from(messages):
    """从已有消息构建内容级判重集合（仅 ai / tool 两类）。

    内容级判重针对「指纹漂移」：抽屉按基于 blocks 的指纹去重，而镜像正文优先用 md；
    AI 流式生成时 blocks 会增长、指纹随之变化，但 md 最终稳定，
    导致同一条消息因指纹漂移被当成新消息、重复入库。
    user 与 system 不纳入（用户可能连发相同的话；指令回执是两次真实执行）。
    @param messages 已有消息列表
    @returns {(role, text)} 集合
    """
    content_seen = set()
    for m in messages:
        r = m.get("role")
        if r in ("ai", "tool"):
            content_seen.add((r, m.get("text") or ""))
    return content_seen


def _skip_item(it, seen, content_seen):
    """判断一条 item 是否应跳过（已入库 或 内容重复）。

    @param it          待入库条目
    @param seen        已入库源 id 集合
    @param content_seen 内容级判重集合
    @returns 应跳过为 True
    """
    sid = str(it.get("source_id") or "")
    # 无源 id 的条目（如网页自己发的）允许直接入库，不去重
    if sid and sid in seen:
        return True
    role = it.get("role") or "user"
    text = str(it.get("text") or "")
    if role in ("ai", "tool", "system") and (role, text) in content_seen:
        return True
    return False


def _make_msg(it, seq):
    """按 item 与分配到的 seq 构造消息对象。

    @param it  待入库条目
    @param seq 分配到的单调递增序号
    @returns 消息对象
    """
    return {
        "seq": seq,
        "id": "w-" + str(seq),
        "role": it.get("role") or "user",
        "text": str(it.get("text") or ""),
        "voice": str(it.get("voice") or ""),
        "voice_text": str(it.get("voice_text") or ""),
        "image": _norm_image(it.get("image")),
        "kind": str(it.get("kind") or ""),
        # key：消息在抽屉消息树里的 key（pid-id 格式），供前端核对块完整性
        "key": str(it.get("key") or ""),
        "ts": int(it.get("ts") or (time.time() * 1000)),
    }


def _init_batch(state):
    """准备一批入库所需的可变上下文。

    seen 用「有序列表 + 集合」双结构：列表保序用于截断，集合用于 O(1) 判定。
    不能用 list(set) 再切片——集合无序，切片会随机丢条目，导致已入库的
    source_id 被误删、该消息再次上报时重新入库（user 消息无内容判重兜底，会重复）。
    @param state 收件箱状态
    @returns 批次上下文（含 seq / messages / added / seen / seen_list / content_seen）
    """
    seen_list = list(state.get("seen") or [])
    messages = state.get("messages") or []
    return {
        "seq": int(state.get("seq") or 0),
        "messages": messages,
        "added": [],
        "seen": set(seen_list),
        "seen_list": seen_list,
        "content_seen": _content_seen_from(messages),
    }


def _apply_item(it, batch):
    """把一条 item 应用进批次上下文；被跳过时返回 False。

    就地更新 batch 的 seq / messages / added / seen 等字段。
    @param it    待入库条目
    @param batch 批次上下文
    @returns 是否真正新增了一条
    """
    if _skip_item(it, batch["seen"], batch["content_seen"]):
        return False
    sid = str(it.get("source_id") or "")
    role = it.get("role") or "user"
    text = str(it.get("text") or "")
    batch["seq"] += 1
    msg = _make_msg(it, batch["seq"])
    batch["messages"].append(msg)
    batch["added"].append(msg)
    if sid and sid not in batch["seen"]:
        batch["seen"].add(sid)
        batch["seen_list"].append(sid)   # 有序列表同步追加，供末尾保序截断
    # 同步累加内容级判重集合：同一批内后续的重复条目据此跳过
    if role in ("ai", "tool", "system"):
        batch["content_seen"].add((role, text))
    return True


def _flush_batch(state, batch):
    """把批次上下文写回收件箱状态并落盘（无新增则不动）。

    @param state 收件箱状态（就地更新）
    @param batch 批次上下文
    """
    if not batch["added"]:
        return
    messages = batch["messages"]
    if len(messages) > MAX_MESSAGES:
        messages = messages[-MAX_MESSAGES:]
    state["seq"] = batch["seq"]
    state["messages"] = messages
    # 已入库源 id 同样限长：只保留最近写入的一批（有序列表保序截断，
    # 不会像 list(set) 那样随机丢条目），避免它本身无界增长。
    state["seen"] = batch["seen_list"][-MAX_MESSAGES * 2:]
    _write_state(state)


def append_many(items):
    """批量入库并去重，返回真正新增的消息列表。

    抽屉上报的是全量切片，同一条消息会被反复上报；本函数按每条 item 的
    source_id（抽屉里的消息 id）去重，只有首次出现才写进收件箱。
    整个批次共用一次读改写，避免逐条写盘。
    逐条判定与构造委托 _init_batch / _apply_item / _flush_batch，本函数只做编排。
    @param items 列表，每项 {source_id, role, text, voice, kind}
    @returns 新增的消息对象列表（按入库顺序）
    """
    with _timed_lock('append_many'):
        state = _read_state()
        batch = _init_batch(state)
        for it in (items or []):
            _apply_item(it, batch)
        _flush_batch(state, batch)
        return batch["added"]


def is_seen(source_id):
    """判断某条源消息是否已入库（用于避免重复做重活，如语音合成）。

    @param source_id 抽屉里的消息 id
    @returns 已入库为 True
    """
    sid = str(source_id or "")
    if not sid:
        return False
    with _timed_lock('is_seen'):
        state = _read_state()
    return sid in set(state.get("seen") or [])


def set_voice(seq, name):
    """把某条消息的语音文件名回填（按需合成完成后调用）。

    只改 voice 字段，不动其它内容；消息不存在则静默返回。
    加锁保证与网页请求线程的读改写互斥。
    @param seq  消息的 seq
    @param name 合成后的音频文件名（相对音频目录）
    @returns 是否真的更新
    """
    try:
        want = int(seq)
    except (TypeError, ValueError):
        return False
    with _timed_lock('set_voice'):
        state = _read_state()
        for m in (state.get("messages") or []):
            if int(m.get("seq") or 0) == want:
                m["voice"] = str(name or "")
                _write_state(state)
                return True
    return False


def get_by_seq(seq):
    """按 seq 取一条消息；不存在返回 None。供按需合成查询 voice/voice_text。"""
    try:
        want = int(seq)
    except (TypeError, ValueError):
        return None
    with _timed_lock('get_by_seq'):
        state = _read_state()
    for m in (state.get("messages") or []):
        if int(m.get("seq") or 0) == want:
            return m
    return None


def list_since(cursor=0, limit=200):
    """拉取游标之后的新消息（增量）。

    @param cursor 上次拿到的最大 seq；传 0 表示首次拉取
    @param limit  单次最多返回条数，避免一次拉太多卡住手机
    @returns {seq, messages}：seq 为当前最新游标，messages 为新消息（按时间正序）
    """
    with _timed_lock('list_since'):
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
    with _timed_lock('recent'):
        state = _read_state()
    messages = state.get("messages") or []
    if limit and len(messages) > limit:
        messages = messages[-limit:]
    return {"seq": int(state.get("seq") or 0), "messages": messages}


def clear():
    """清空收件箱（供调试或用户主动重置）。"""
    with _timed_lock('clear'):
        _write_state(_empty_state())
