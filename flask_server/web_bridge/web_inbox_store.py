"""网页版机器人 —— 收件箱持久化层

职责：把收件箱状态「读盘 / 写盘」，带内存缓存与耗时埋点。
从 web_inbox.py 抽出，使主模块专注于消息逻辑、保持在行数上限内，
也让「持久化 + 缓存 + 慢 IO 埋点」这一独立关注点集中一处。

缓存策略：比对文件签名（mtime 纳秒 + 大小），未变则直接复用内存对象，
避免每次读取都解析整个大 JSON。

依赖：json、paths、app_log
"""
import json
import threading
import time

import paths
import app_log

# 慢 IO 阈值（毫秒）：读盘解析或写盘超过此值即告警。
# 收件箱读写都发生在持锁期间，其耗时直接决定「等待收件箱锁的界面轮询」
# 要等多久，故记录耗时、消息数与字节数，便于判断界面卡顿是否随体积增长。
_SLOW_IO_MS = 50.0

# 内存缓存：状态对象 + 文件签名。
_cache = None
_cache_sig = None


def file_sig():
    """取收件箱文件的签名（mtime 纳秒 + 大小）；文件不存在返回 None。"""
    try:
        st = paths.WEB_INBOX_PATH.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def empty_state():
    """收件箱的初始状态：空消息列表 + 游标归零 + 已入库源 id 集合。

    seen 用于按「源消息 id」去重：抽屉每次上报的是全量可见切片，
    若不去重，同一轮对话会被反复写进收件箱。
    """
    return {"seq": 0, "messages": [], "seen": []}


def sanitize_state(data):
    """把读到的原始数据规整为合法状态（字段类型不对时用兜底值）。

    @param data 从磁盘 JSON 解析出的对象
    @returns {seq, messages, seen} 状态字典
    """
    if not isinstance(data, dict):
        return empty_state()
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


def read_state():
    """读取收件箱状态（带缓存）。不存在或损坏时返回空结构。

    损坏时不抛异常：收件箱是「尽力而为」的展示缓存，
    宁可当作空箱重新开始，也不能让网页版整个不可用。
    """
    global _cache, _cache_sig
    import time as _t
    path = paths.WEB_INBOX_PATH
    sig = file_sig()
    # 缓存命中：签名未变直接复用，避免重复解析大 JSON
    if _cache is not None and sig is not None and sig == _cache_sig:
        return _cache
    if not path.exists():
        _cache = empty_state()
        _cache_sig = None
        return _cache
    _t0 = _t.perf_counter()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        app_log.warn("[web]", "读取收件箱失败，按空箱处理：", e)
        _cache = empty_state()
        _cache_sig = sig
        return _cache
    _ms = (_t.perf_counter() - _t0) * 1000.0
    if _ms >= _SLOW_IO_MS:
        app_log.warn("[web][inbox]", "读盘解析耗时=%.0fms" % _ms)
    # 字段兜底：外部改坏文件时不至于让后续逻辑崩在 None 上
    _cache = sanitize_state(data)
    _cache_sig = sig
    return _cache


# 待写状态与后台写线程：内存缓存立即更新，磁盘写盘异步执行。
# 收件箱一次全量写可达 700KB / 600ms，若同步写会卡住上报链路；
# 改为「只保留最后一次状态、由单线程串行写盘」，多个写请求自动合并。
_pending = None
_pending_lock = threading.Lock()
_pending_event = threading.Event()
_writer_started = False


def _write_state_now(state):
    """真正执行一次写盘（仅供后台线程调用）。

    @param state 要写入的状态对象
    """
    global _cache_sig
    path = paths.WEB_INBOX_PATH
    _t0 = time.perf_counter()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(state, ensure_ascii=False)
        path.write_text(text, encoding="utf-8")
    except Exception as e:
        app_log.warn("[web]", "写回收件箱失败：", e)
        return
    _ms = (time.perf_counter() - _t0) * 1000.0
    if _ms >= _SLOW_IO_MS:
        app_log.warn("[web][inbox]",
                     "写盘耗时=%.0fms 消息=%d 字节=%d"
                     % (_ms, len(state.get("messages") or []), len(text)))
    _cache_sig = file_sig()


def _writer_loop():
    """后台写盘循环：每次取最新待写状态，写完再取下一个。

    合并语义：写盘期间若又有新状态进来，只保留最新的那份，
    中间态直接丢弃——收件箱是全量快照，后一份天然覆盖前一份。
    """
    global _pending
    while True:
        _pending_event.wait()
        with _pending_lock:
            state = _pending
            _pending = None
            _pending_event.clear()
        if state is not None:
            _write_state_now(state)


def _ensure_writer():
    """惰性启动后台写线程（守护线程，随进程退出）。"""
    global _writer_started
    if _writer_started:
        return
    with _pending_lock:
        if _writer_started:
            return
        t = threading.Thread(target=_writer_loop, daemon=True, name="inbox-writer")
        t.start()
        _writer_started = True


def flush_pending(timeout=3.0):
    """等待待写状态落盘（进程退出前调用）。

    异步写盘牺牲了「返回即落盘」的保证：进程被优雅停止时，
    最后一份可能还在队列里。此处给一个有时限的等待，
    把「退出瞬间的丢失」压缩到可忽略。

    @param timeout 最长等待秒数
    @returns 是否已无待写数据
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        with _pending_lock:
            if _pending is None:
                return True
        time.sleep(0.02)
    return False


def write_state(state):
    """更新内存缓存并安排后台写盘，立即返回。

    内存缓存同步更新：紧随其后的读取能立刻看到新内容，不必等磁盘。
    磁盘写盘异步执行：调用方（上报链路）不再为 700KB 全量写等待。
    极端情况下进程崩溃可能丢失最后一次未落盘的写——收件箱是展示缓存，
    抽屉下次上报会重新补上，可接受。

    @param state 新的收件箱状态
    """
    global _cache, _pending
    _cache = state
    _ensure_writer()
    with _pending_lock:
        _pending = state
    _pending_event.set()
