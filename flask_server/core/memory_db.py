"""AI 工具调用镜像插件 —— 记忆系统：数据库层

职责：
  1. 管理记忆库 SQLite 连接（单文件、进程内、线程安全）；
  2. 建表：nodes / edges / cards / plans / revision_log 五张表；
  3. 建 FTS5 全文索引（关键词检索）；
  4. 提供向量存取与暴力余弦检索（numpy 实现，零外部依赖）。

设计要点：
  - 全库只有一个 SQLite 文件（paths.MEMORY_DB_PATH），启动即可用；
  - 连接按线程隔离：SQLite 连接不可跨线程共享，用 threading.local 保存；
  - 向量检索不依赖向量库：记忆库量级小，numpy 暴力余弦足够，
    将来若换 sqlite-vec，只需替换 search_vectors 内部实现，调用方不动。

依赖：paths（路径）、sqlite3、threading、numpy
"""
import sqlite3
import threading
import time

import numpy as np

import paths
import app_log

# 线程局部存储：每个线程持有一份独立连接（SQLite 连接不可跨线程共享）
_local = threading.local()

# 建表语句：五张表一次建齐，IF NOT EXISTS 保证幂等
_SCHEMA = [
    # 节点表：对应消息树 msgTree 的 value，另含蒸馏层字段
    """CREATE TABLE IF NOT EXISTS nodes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_id      TEXT UNIQUE,
        conv_id     TEXT,
        site_key    TEXT,
        parent_id   INTEGER DEFAULT 0,
        source      TEXT,
        role        TEXT,
        name        TEXT,
        blocks      TEXT,
        deleted     INTEGER DEFAULT 0,
        essence     TEXT,
        keywords    TEXT,
        tier        TEXT DEFAULT 'temp',
        hit_count   INTEGER DEFAULT 0,
        strength    REAL DEFAULT 0.5,
        vector      BLOB,
        created_at  INTEGER,
        last_hit_at INTEGER
    )""",
    # 边表：对应消息树 msgTree 的 key，另含突触边
    """CREATE TABLE IF NOT EXISTS edges (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        src_node       INTEGER,
        dst_node       INTEGER,
        kind           TEXT,
        weight         REAL DEFAULT 1.0,
        created_at     INTEGER,
        last_active_at INTEGER,
        UNIQUE(src_node, dst_node, kind)
    )""",
    # 卡片表：对应节点内的 cards（工具执行状态与结果）
    """CREATE TABLE IF NOT EXISTS cards (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id     INTEGER,
        block_id    TEXT,
        tool        TEXT,
        status      TEXT,
        result      TEXT,
        finished_at INTEGER
    )""",
    # 计划暂存表：双接口 A 专用
    """CREATE TABLE IF NOT EXISTS plans (
        plan_id    TEXT PRIMARY KEY,
        session_id TEXT,
        text       TEXT,
        created_at INTEGER
    )""",
    # 修订日志表：语义修订只追加不覆盖
    """CREATE TABLE IF NOT EXISTS revision_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id    INTEGER,
        old_text   TEXT,
        new_text   TEXT,
        reason     TEXT,
        created_at INTEGER
    )""",
    # 笔记表：承载「每日记忆」与「错题本」两类文本记忆（原 Markdown 迁移入此）
    #   kind='journal'  → 每日记忆条目（按日期组织）
    #   kind='notebook' → 错题本条目（永久累积）
    #   day 仅 journal 使用（YYYY-MM-DD）；其余为 NULL
    """CREATE TABLE IF NOT EXISTS notes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        kind       TEXT,
        day        TEXT,
        node_id    INTEGER DEFAULT 0,
        text       TEXT,
        keywords   TEXT,
        created_at INTEGER
    )""",
    # 会话表：存会话级元数据与树结构索引（前端走后端查询时重建消息树用）
    """CREATE TABLE IF NOT EXISTS conversations (
        conv_id        TEXT,
        site_key       TEXT,
        title          TEXT,
        page_url       TEXT,
        visible_keys   TEXT,
        branch_keys    TEXT,
        external_cards TEXT,
        orphan_slice   TEXT,
        updated_at     INTEGER,
        PRIMARY KEY (conv_id, site_key)
    )""",
]

# 索引：按会话/父节点/边源查询
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_nodes_conv ON nodes(conv_id, site_key)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id)",
    "CREATE INDEX IF NOT EXISTS idx_nodes_source ON nodes(source)",
    "CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_node)",
    "CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_node)",
    "CREATE INDEX IF NOT EXISTS idx_cards_node ON cards(node_id)",
]


def get_conn():
    """取得当前线程的记忆库连接；首次调用时建库、建表、建索引。"""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        return conn
    # 确保目录存在：记忆库目录可能首次创建
    paths.MEMORY_DB_DIR.mkdir(parents=True, exist_ok=True)
    # timeout=15：连接级等待锁的秒数（默认仅 5 秒）。
    # 多人/多线程同时写时，5 秒不够就容易直接报 database is locked，
    # 放宽到 15 秒，给排队等锁的写入更多耐心。
    conn = sqlite3.connect(str(paths.MEMORY_DB_PATH), timeout=15.0)
    conn.row_factory = sqlite3.Row
    # WAL 模式：读写并发更好，且写入不阻塞读取
    conn.execute("PRAGMA journal_mode=WAL")
    # busy_timeout：与 timeout 双保险，单位毫秒；遇锁时自旋等待而非立即报错
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA synchronous=NORMAL")
    # 慢 SQL 追踪：记录执行超过阈值的语句，用于定位「哪条 SQL 卡住」。
    # 诊断用，不改变查询行为。
    _install_slow_query_trace(conn)
    _ensure_schema(conn)
    _local.conn = conn
    app_log.info("[db][%s] 建立记忆库连接" % threading.current_thread().name)
    return conn


# 慢 SQL 阈值（毫秒）：超过即记日志
_SLOW_SQL_MS = 100


def _install_slow_query_trace(conn):
    """给连接装一个 SQL 追踪钩子：执行超阈值的语句落日志。

    SQLite 的 set_trace_callback 在每条语句执行前回调；
    这里记录语句开始时刻，在下一句或提交时结算耗时，从而发现慢查询。
    记录里带线程名，便于区分是「请求线程」还是「后台调度线程」在拖。
    """
    state = {"t0": None, "sql": ""}

    def _trace(sql):
        now = time.time()
        # 结算上一句的耗时
        if state["t0"] is not None:
            ms = (now - state["t0"]) * 1000.0
            if ms >= _SLOW_SQL_MS:
                app_log.warn("[db][%s] 慢SQL %.1fms: %s" % (
                    threading.current_thread().name, ms,
                    " ".join(state["sql"].split())[:120]))
        state["t0"] = now
        state["sql"] = sql or ""

    try:
        conn.set_trace_callback(_trace)
    except Exception:
        pass


def _ensure_schema(conn):
    """建表、建索引、建 FTS5 全文索引（全部幂等）。"""
    for sql in _SCHEMA:
        conn.execute(sql)
    for sql in _INDEXES:
        conn.execute(sql)
    # FTS5 全文索引：把「精华 + 关键词」做全文检索用。
    # 用外部内容表关联 nodes，避免重复存储。
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5("
            "essence, keywords, content='nodes', content_rowid='id')"
        )
    except sqlite3.OperationalError:
        # FTS5 不可用时降级：检索层会自动回退到 LIKE 匹配
        pass
    conn.commit()


# ---------------- 批量提交（延迟提交） ----------------
# 用途：批量写（如保存整个会话）时，避免每个字段都单独提交一次，
# 攒到最后一次性提交，大幅减少抢写锁的次数与来回开销。
# 计数存线程局部：SQLite 连接按线程隔离，提交节奏也应逐线程独立。


def begin_batch():
    """进入批量模式：此后本线程的写操作不再逐个提交。"""
    n = getattr(_local, "defer", 0)
    _local.defer = n + 1


def end_batch(conn):
    """退出批量模式；计数归零时统一提交一次。"""
    n = getattr(_local, "defer", 0)
    if n > 0:
        _local.defer = n - 1
    if getattr(_local, "defer", 0) == 0:
        conn.commit()


def maybe_commit(conn):
    """按需提交：批量模式中跳过，非批量模式立即提交。"""
    if getattr(_local, "defer", 0) == 0:
        conn.commit()


def vec_to_blob(vec):
    """把向量（list / np.ndarray）序列化为 BLOB；None 或空返回 None。"""
    if vec is None:
        return None
    arr = np.asarray(vec, dtype=np.float32)
    if arr.size == 0:
        return None
    return arr.tobytes()


def blob_to_vec(blob):
    """把 BLOB 还原为 float32 向量；空返回 None。"""
    if not blob:
        return None
    return np.frombuffer(blob, dtype=np.float32)


def cosine_topk(query_vec, candidates, top_k):
    """对候选向量做暴力余弦检索，返回 [(node_id, 相似度)] 降序。

    @param query_vec 查询向量（list / np.ndarray）
    @param candidates [(node_id, blob)] 候选集
    @param top_k 返回条数
    """
    q = np.asarray(query_vec, dtype=np.float32)
    qn = float(np.linalg.norm(q))
    if qn == 0:
        return []
    scored = []
    for node_id, blob in candidates:
        v = blob_to_vec(blob)
        if v is None or v.shape != q.shape:
            continue
        vn = float(np.linalg.norm(v))
        if vn == 0:
            continue
        sim = float(np.dot(q, v) / (qn * vn))
        scored.append((node_id, sim))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def reset_for_tests(db_path):
    """测试专用：关闭当前连接，把库路径切到临时文件后重连。

    只在自测脚本里调用，绝不触碰真实库。
    调用方需先把 paths.MEMORY_DB_PATH 指向临时文件，再调本函数。
    @param db_path 临时库路径（Path）
    """
    global _local
    # 关闭当前线程的旧连接，丢弃线程局部，使下次 get_conn 用新路径重连
    old = getattr(_local, "conn", None)
    if old is not None:
        try:
            old.close()
        except Exception:
            pass
    _local = threading.local()
    import paths as _paths
    _paths.MEMORY_DB_PATH = db_path
    return get_conn()
