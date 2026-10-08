"""AI 工具调用镜像插件 —— 界面请求优先级（后台维护主动让路）

背景：
  SQLite 同一时刻只允许一个写者，后台维护（全量衰减重算）会分批长时间写库，
  与界面里的写操作争抢写锁。界面响应是最高优先级，且操作轻量（毫秒级即可完成），
  故约定：维护每批之间若发现「有界面请求在进行」，立刻让路，等界面做完再继续。

工作方式：
  - 计数由 app.py 的请求钩子维护：请求进入 ui_request_enter()，结束 ui_request_exit()；
  - 维护每批写库后调用 maintenance_yield()：若有界面请求在跑，小步等待至其完成；
  - 设最长等待上限，避免界面持续繁忙时维护被无限饿死。

为何独立成模块：
  本机制是「调度策略」，与数据库连接/建表等存储职责不同；独立后 memory_db 保持精简，
  也让「谁在让路、按什么规则让」集中一处、便于审阅。

依赖：threading、time
"""
import threading
import time

# 进行中的界面请求计数：请求进入 +1、结束 -1。
_ui_active = 0
_ui_lock = threading.Lock()


def ui_request_enter():
    """登记一个界面请求开始（由请求进入钩子调用）。"""
    global _ui_active
    with _ui_lock:
        _ui_active += 1


def ui_request_exit():
    """登记一个界面请求结束（由请求结束钩子调用）。"""
    global _ui_active
    with _ui_lock:
        if _ui_active > 0:
            _ui_active -= 1


def ui_active_count():
    """当前进行中的界面请求数。"""
    with _ui_lock:
        return _ui_active


def maintenance_yield(step=0.05, max_wait=0.5):
    """后台维护让路：若有界面请求在进行，小步等待直至其完成。

    每批写库后调用。界面请求通常毫秒级完成，故等待极短；
    设 max_wait 上限，避免界面持续繁忙时维护被无限饿死。
    @param step     每次检查的等待步长（秒）
    @param max_wait 单次让路的最长等待（秒）
    @returns 是否真的等待过（True 表示发生过让路）
    """
    # 用真实时间判断上限：sleep(step) 的实际耗时受系统计时精度影响
    # （Windows 上可能远大于 step），若按标称步长累加会低估、导致实际等待超时。
    deadline = time.time() + max_wait
    yielded = False
    while ui_active_count() > 0 and time.time() < deadline:
        time.sleep(step)
        yielded = True
    return yielded
