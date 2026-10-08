"""AI 工具调用镜像插件 —— 记忆系统：数据库层

职责：
  1. 管理记忆库 SQLite 连接（单文件、进程内、线程安全）；
  2. 建表：nodes / edges / cards / plans / revision_log / notes / conversations 七张表；
  3. 清理历史遗留的 FTS5 虚表（关键词检索实际走 LIKE，见 memory_search）；
  4. 提供向量序列化与暴力余弦检索（numpy 实现，零外部依赖）。

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

# 建表语句：七张表一次建齐，IF NOT EXISTS 保证幂等
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
    #   keywords：导致关联的关键词（JSON 数组），仅突触边使用，供前端解释连线原因
    """CREATE TABLE IF NOT EXISTS edges (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        src_node       INTEGER,
        dst_node       INTEGER,
        kind           TEXT,
        weight         REAL DEFAULT 1.0,
        keywords       TEXT,
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
    """取得当前线程的记忆库连接；首次调用时建立连接。

    建表（含 FTS5 虚拟表）只在进程内做一次，不在每个新连接上重复执行。
    原因：Flask 每个请求开新线程，每个新线程首次连库若都跑一遍建表语句，
    在有数据量后 CREATE VIRTUAL TABLE ... fts5 会耗时数秒并拿写锁，
    把全部请求堵死（曾观察到单条建表语句 8-13 秒、请求几十秒超时）。
    """
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
    # WAL 是数据库级设置（写入文件头，永久生效），只需设一次。
    # 每个新连接都设一遍会在多线程同时连库时互相冲突、报 database is locked。
    _ensure_wal_once(conn)
    # busy_timeout：与 timeout 双保险，单位毫秒；遇锁时自旋等待而非立即报错
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA synchronous=NORMAL")
    # 慢 SQL 追踪：记录执行超过阈值的语句，用于定位「哪条 SQL 卡住」。
    # 诊断用，不改变查询行为。
    _install_slow_query_trace(conn)
    # 建表只在进程内做一次（详见 _ensure_schema_once）
    _ensure_schema_once(conn)
    _local.conn = conn
    app_log.info("[db][%s] 建立记忆库连接" % threading.current_thread().name)
    return conn


def close_conn():
    """关闭当前线程的记忆库连接，并从线程局部清除。

    用途：请求线程处理完毕后及时释放连接，不再依赖「线程退出 + GC」的
    隐式回收时机。幂等：未建连接或重复调用均安全。

    只关闭「当前线程」的连接——后台长期线程（调度、工具池）各自的连接
    不受影响，它们照常复用。关闭后本线程再次 get_conn 会重建新连接。
    """
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            # 关闭失败不影响调用方（连接本就要丢弃）
            pass
        # 清除线程局部引用，确保下次 get_conn 重建
        try:
            del _local.conn
        except Exception:
            _local.conn = None


# 进程级 WAL 设置标志：WAL 是库级设置，只设一次，避免多线程连库时冲突。
_wal_lock = threading.Lock()
_wal_ready = False


def _ensure_wal_once(conn):
    """把 journal_mode 设为 WAL，只在进程内做一次。

    WAL 写入数据库文件头、永久生效；多线程各自执行会在并发连库时报
    database is locked。故加锁只做一次，其余连接直接跳过。
    """
    global _wal_ready
    if _wal_ready:
        return
    with _wal_lock:
        if _wal_ready:
            return
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            # 已被其它进程设为 WAL 或暂时锁住：不阻断，继续用连接
            pass
        _wal_ready = True


# 进程级建表标志：确保建表语句（含 FTS5 虚拟表）全程只执行一次。
_schema_lock = threading.Lock()
_schema_ready = False


def _ensure_schema_once(conn):
    """建表只在进程内做一次；后续新线程连接直接跳过，避免重复建表拖垮请求。"""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        _ensure_schema(conn)
        _schema_ready = True


# 慢 SQL 阈值（毫秒）：超过即记日志
_SLOW_SQL_MS = 100

# 进度回调粒度：SQLite 每执行多少条虚拟机指令回调一次。
# 取值偏大以减少回调开销；短语句可能一次都不触发，自然不计时、不告警——
# 这正是期望行为（短查询本就不该告警）。
_SQL_PROGRESS_INTERVAL = 2000


def _install_slow_query_trace(conn):
    """给连接装慢 SQL 追踪：只统计语句「真正执行」的时间，不含线程空闲。

    为什么不能只用 set_trace_callback：
        它只在每条语句「执行前」回调一次。若用「两次回调的时间差」当作
        上一条 SQL 的耗时，就把两条语句之间线程的全部空闲时间也算了进去——
        后台调度线程跑完一轮后 sleep(1800) 约 30 分钟，这 30 分钟会被误记到
        它上一条 SQL 头上，产生「慢SQL 1800000ms」这类假告警。

    改用 set_progress_handler 计时：
        它在语句「执行过程中」周期性回调，只在 SQL 真运行时触发，sleep 期间
        不会触发。一次执行期内「首次回调 → 末次回调」的时间差即为真实执行
        时长，不含任何空闲。结算时机沿用「下一条语句执行前」（trace 回调里）。
    记录里带线程名，便于区分是「请求线程」还是「后台调度线程」在拖。
    """
    state = {"sql": "", "first_tick": None, "last_tick": None}
    try:
        conn.set_trace_callback(lambda sql: _slow_sql_trace(state, sql))
        conn.set_progress_handler(lambda: _slow_sql_progress(state), _SQL_PROGRESS_INTERVAL)
    except Exception:
        pass


def _slow_sql_settle(state):
    """结算当前语句：只有发生过进度回调（即真的执行过）才计时与告警。

    @param state 追踪状态字典（sql / first_tick / last_tick）
    """
    if state["first_tick"] is not None:
        ms = (state["last_tick"] - state["first_tick"]) * 1000.0
        if ms >= _SLOW_SQL_MS:
            app_log.warn("[db][%s] 慢SQL %.1fms: %s" % (
                threading.current_thread().name, ms,
                " ".join(state["sql"].split())[:120]))


def _slow_sql_trace(state, sql):
    """语句执行前的 trace 回调：先结算上一条，再开始记录新一条。

    @param state 追踪状态字典
    @param sql   即将执行的语句
    """
    _slow_sql_settle(state)
    state["sql"] = sql or ""
    state["first_tick"] = None
    state["last_tick"] = None


def _slow_sql_progress(state):
    """语句执行中的进度回调：记录首次与末次时刻；返回 0 表示不中止查询。

    @param state 追踪状态字典
    @returns 恒为 0（不中止查询）
    """
    now = time.time()
    if state["first_tick"] is None:
        state["first_tick"] = now
    state["last_tick"] = now
    return 0


def _migrate_columns(conn):
    """兼容迁移：为已存在的旧库补「后加的列」。

    CREATE TABLE IF NOT EXISTS 只对「表不存在」时建表；表已存在时它不改动，
    故后加的列必须显式 ALTER TABLE ADD COLUMN。此函数幂等：列已存在则跳过。
    """
    # (表名, 列名, 列定义) —— 新增列时在此登记一行即可
    migrations = [
        ("edges", "keywords", "TEXT"),   # 突触边：导致关联的关键词（JSON 数组）
    ]
    for table, col, decl in migrations:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(%s)" % table).fetchall()]
        if col not in cols:
            conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, decl))


def _ensure_schema(conn):
    """建表、建索引、建 FTS5 全文索引（全部幂等）。"""
    for sql in _SCHEMA:
        conn.execute(sql)
    for sql in _INDEXES:
        conn.execute(sql)
    # 兼容迁移：为已存在的旧库补「后加的列」。
    # CREATE TABLE IF NOT EXISTS 不会改动已存在的表，故新列必须显式 ALTER。
    _migrate_columns(conn)
    # 清理历史遗留的 FTS5 虚表 nodes_fts：
    # 早期曾建该虚表想走全文检索，但 FTS5 默认分词器把连续汉字当单词元，
    # 中文短语匹配失效，检索已改走 LIKE 子串匹配（见 memory_search._fts_search）。
    # 该虚表建后无人查询，且建表本身在数据量后耗时数秒并拿写锁，故移除。
    # DROP IF EXISTS 幂等：新库无此表时几无开销，旧库则清理掉遗留。
    try:
        conn.execute("DROP TABLE IF EXISTS nodes_fts")
    except sqlite3.OperationalError:
        # FTS5 模块不可用时忽略：本就没有该虚表
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
    global _local, _schema_ready, _wal_ready
    # 复位建表 / WAL 标志：否则切到临时库后 _ensure_schema_once 直接返回，
    # 临时库不会建表（真实库若已建过表，本进程内 _schema_ready 恒为 True）。
    _schema_ready = False
    _wal_ready = False
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
