"""AI 工具调用镜像插件 —— 记忆系统：后台调度

职责：把「应当全自动」的记忆维护任务从手动接口解放出来，
由后台守护线程周期性执行，落实方案「事件层全自动」的承诺。

自动执行：
  1. 衰减计算（memory_decay.recompute_all）—— 强度重算 + 自动升降级；
  2. 事件聚类（memory_events.cluster_events）—— 跨会话同主题发言聚成事件。

设计要点：
  - 守护线程 + 长间隔 sleep，绝不在请求路径上执行，不阻塞接口；
  - 每轮整体 try/except 兜底，单轮失败不退出循环，下轮继续；
  - 用模块级标志防止重复启动；
  - 间隔可调，默认 30 分钟（衰减按天计，无需高频）。

依赖：memory_decay、memory_events、threading、time
"""
import threading
import time

import app_log
import memory_decay
import memory_events

# 默认运行间隔（秒）：30 分钟
DEFAULT_INTERVAL = 1800
# 模块级标志：防止重复启动多个调度线程
_started = False
_lock = threading.Lock()


def run_once():
    """执行一轮维护：衰减 + 聚类。返回两步骤各自的结果，异常吞掉不抛。

    @return dict { decay, events, errors }
    """
    result = {"decay": None, "events": None, "errors": []}
    t0 = time.time()
    # 记开始：后台重活若与请求抢锁，日志里能看出「它正在跑」
    app_log.info("[mem][sched] 维护轮次开始")
    try:
        result["decay"] = memory_decay.recompute_all()
    except Exception as e:
        result["errors"].append("decay: %s" % e)
    try:
        result["events"] = memory_events.cluster_events()
    except Exception as e:
        result["errors"].append("events: %s" % e)
    # 记结束与耗时：这轮跑了多久，直接决定它占锁时间
    app_log.info("[mem][sched] 维护轮次结束 耗时=%.1fms errors=%s" % (
        (time.time() - t0) * 1000.0, result["errors"] or "无"))
    return result


def _loop(interval):
    """调度主循环：先跑一轮，再按间隔周期跑。守护线程，进程退出即止。"""
    while True:
        try:
            run_once()
        except Exception as e:
            # 看门狗兜底：任何意外都不让循环退出
            print("[memory] 调度轮次异常：%s" % e)
        time.sleep(interval)


def start_background_tasks(interval=DEFAULT_INTERVAL):
    """启动后台调度线程（幂等：重复调用只启动一次）。

    @param interval 运行间隔（秒）
    @return 是否本次真正启动了线程
    """
    global _started
    with _lock:
        if _started:
            return False
        _started = True
    t = threading.Thread(target=_loop, args=(interval,), daemon=True)
    t.start()
    return True
