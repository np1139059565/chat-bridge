"""AI 工具调用镜像插件 —— run_command 异步任务

职责：把耗时的外部命令从「请求线程同步干等」改为「后台执行 + 轮询取结果」，
解决网页版机器人因某条命令跑十几秒、把整个指令请求拖住而卡顿的问题。

工作方式：
  1. submit(params) 把命令投入后台队列，立即返回 task_id；
  2. 后台单 worker 串行取任务，调用 run_command 的实现去执行；
  3. get(task_id) 查询状态（pending / running / done / failed）与结果。

设计要点：
  - 单 worker 串行：与项目其它后台队列（会话保存、蒸馏）保持一致的并发模型，
    避免多条重命令同时起、把机器拖垮；
  - 任务表为内存字典：进程重启即丢；命令任务是一次性的，不做持久化；
  - 保留上限 + 过期清理：已完成任务超量或超时即淘汰，防止内存无限增长。

依赖：run_command_impl、threading、collections、time
"""
import collections
import threading
import time

import app_log
import run_command_impl
import serial_worker

# 任务表上限：超过后淘汰最旧的「已完成」任务，防止内存无限增长
_MAX_TASKS = 200

# 任务表：task_id -> dict
#   { id, status, params, result, error, created_at, finished_at }
# status 取值：pending（排队中）/ running（执行中）/ done（完成）/ failed（失败）
_tasks = {}
# 入队顺序：用于淘汰最旧任务
_tasks_order = collections.deque()
# 统一锁：保护任务表与入队顺序，线程安全
_lock = threading.Lock()
# task_id 序号：与时间戳组合，保证同一秒内多次提交也不重号
_seq = 0

# 待执行任务队列：并发骨架统一走共享模块 serial_worker。
# task_id 本身唯一，故以它作 key，天然不发生去重（每个任务都会被处理）。
_task_worker = serial_worker.SerialWorker(
    lambda tid: _run_task(tid), thread_name="cmd-task-worker")


def _now():
    """当前 Unix 时间戳（秒）。"""
    return int(time.time())


def _prune_locked():
    """淘汰超额的最旧「已完成」任务（须在持锁状态下调用）。

    只淘汰已结束（done / failed）的任务；排队与执行中的任务永不淘汰，
    否则会把正在跑的任务从表里抹掉、查询时变成「未知任务」。
    """
    while len(_tasks) > _MAX_TASKS:
        # 从头找第一个已结束的任务淘汰
        victim = None
        for tid in list(_tasks_order):
            t = _tasks.get(tid)
            if t and t["status"] in ("done", "failed"):
                victim = tid
                break
        if victim is None:
            # 全部在跑，暂不淘汰，等下一轮
            return
        _tasks.pop(victim, None)
        try:
            _tasks_order.remove(victim)
        except ValueError:
            pass


def submit(params):
    """提交一条命令到后台队列，立即返回 task_id（不等待执行）。

    @param params run_command 的参数字典（language / command / cwd / timeout）
    @return task_id 字符串
    """
    global _seq
    # 复制一份参数：避免调用方提交后再改动，影响后台执行
    safe_params = dict(params or {})
    with _lock:
        _seq += 1
        task_id = "cmd-%d-%d" % (_now(), _seq)
        _tasks[task_id] = {
            "id": task_id,
            "status": "pending",
            "params": safe_params,
            "result": None,
            "error": None,
            "created_at": _now(),
            "finished_at": None,
        }
        _tasks_order.append(task_id)
        _prune_locked()
    _task_worker.submit(task_id, task_id)
    app_log.info("[cmd][async] 入队 task=%s lang=%s" % (
        task_id, safe_params.get("language")))
    return task_id


def get(task_id):
    """查询任务状态与结果；任务不存在返回 None。

    @param task_id 提交时返回的任务号
    @return 任务字典的浅拷贝，或 None
    """
    with _lock:
        t = _tasks.get(task_id)
        if t is None:
            return None
        return dict(t)


def _run_task(task_id):
    """执行单个任务：调 run_command 实现，结果写回任务表。

    单任务异常不抛出，转为 failed 状态，避免中断整个队列。
    @param task_id 任务号
    """
    with _lock:
        t = _tasks.get(task_id)
        if t is None:
            return
        t["status"] = "running"
        params = t["params"]
    t0 = time.perf_counter()
    try:
        result = run_command_impl.t_run_command(params)
        with _lock:
            t = _tasks.get(task_id)
            if t is not None:
                t["status"] = "done"
                t["result"] = result
                t["finished_at"] = _now()
    except Exception as e:
        with _lock:
            t = _tasks.get(task_id)
            if t is not None:
                t["status"] = "failed"
                t["error"] = str(e)
                t["finished_at"] = _now()
    ms = (time.perf_counter() - t0) * 1000.0
    app_log.info("[cmd][async] 完成 task=%s 耗时=%.1fms" % (task_id, ms))
