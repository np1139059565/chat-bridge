"""记忆系统：数据库诊断层

职责：
  1. 慢 SQL 追踪：只统计语句真正执行的时间，排除线程空闲造成的假告警；
  2. 建连耗时累计统计：回答「一共连了多少次、慢了多少次、最慢多久」。

设计要点：
  - 与连接管理（memory_db）解耦：诊断逻辑独立成模块，主模块只保留连接与建表；
  - 统计状态用模块级变量 + 锁保护，多线程下计数不丢；
  - 追踪安装失败不阻断业务，但一定留日志，避免「以为在监控、实际没有」。

依赖：app_log（日志）、threading、time
"""
import threading
import time

import app_log

# 慢 SQL 阈值（毫秒）：超过即记日志
_SLOW_SQL_MS = 100

# 进度回调粒度：SQLite 每执行多少条虚拟机指令回调一次。
# 取值偏大以减少回调开销；短语句可能一次都不触发，自然不计时、不告警——
# 这正是期望行为（短查询本就不该告警）。
_SQL_PROGRESS_INTERVAL = 2000


def install_slow_query_trace(conn):
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

    @param conn 数据库连接
    """
    state = {"sql": "", "first_tick": None, "last_tick": None}
    try:
        conn.set_trace_callback(lambda sql: _slow_sql_trace(state, sql))
        conn.set_progress_handler(lambda: _slow_sql_progress(state), _SQL_PROGRESS_INTERVAL)
    except Exception as e:
        # 追踪安装失败不影响查询本身，但要记录，避免「以为有慢查询监控、实际没有」
        app_log.warn("[db] 安装慢 SQL 追踪失败：%s" % e)


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


# 建连耗时统计：累计次数、慢次数、最长耗时。
# 逐次打 WARN 只能看到零散记录，累计值才能回答「到底慢了多少次」。
_CONN_STATS = {"total": 0, "slow": 0, "max_ms": 0.0}
_CONN_STATS_LOCK = threading.Lock()
_CONN_SLOW_MS = 200.0


def record_conn_cost(ms):
    """累计一次建连耗时；超过阈值时额外记一条 WARN。

    @param ms 本次建连耗时（毫秒）
    """
    with _CONN_STATS_LOCK:
        _CONN_STATS["total"] += 1
        if ms > _CONN_STATS["max_ms"]:
            _CONN_STATS["max_ms"] = ms
        is_slow = ms >= _CONN_SLOW_MS
        if is_slow:
            _CONN_STATS["slow"] += 1
        total = _CONN_STATS["total"]
        slow = _CONN_STATS["slow"]
        max_ms = _CONN_STATS["max_ms"]
    if is_slow:
        app_log.warn("[db][%s] 建立记忆库连接 耗时=%.0fms（累计 慢%d/%d 次，最长%.0fms）" % (
            threading.current_thread().name, ms, slow, total, max_ms))


def conn_stats():
    """返回建连耗时统计快照，供诊断接口或日志汇总使用。

    @returns dict：total 总建连次数 / slow 慢建连次数 / max_ms 最长耗时
    """
    with _CONN_STATS_LOCK:
        return dict(_CONN_STATS)
