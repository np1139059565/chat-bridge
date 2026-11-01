"""AI 工具调用镜像插件 —— 请求全链路追踪

职责：给每个请求一个短 id，记录它的进入、各阶段耗时与离开，
让「卡在哪一步」在日志里一眼可见。

背景：此前只能看到「请求进来、多久后出去」，看不到中间耗在哪。
卡顿排查需要区分：等锁？读盘？调工具？渲染？——三者处置方式完全不同。

设计：
  - 用 Flask 的 g 保存当前请求的追踪上下文，请求结束自动丢弃；
  - mark() 记录阶段耗时，累计超过阈值时按阶段排序打一条 WARN；
  - 界面请求（/api/web/*）一律 INFO 落盘，手机端看不到控制台，只能靠服务端日志。

依赖：flask、time、app_log
"""
import time

from flask import g

import app_log

# 阶段累计超过该值（毫秒）即打一条含各阶段耗时的 WARN。
# 取 300ms：界面请求正常在几十毫秒内完成，超过 300ms 用户已能感到迟滞。
_SLOW_TOTAL_MS = 300.0


def begin(label):
    """开启一次请求追踪；已存在时不覆盖（同一请求只追踪一次）。

    @param label 追踪标签，通常是「方法 路径」
    """
    if getattr(g, "_trace", None) is not None:
        return
    g._trace = {
        "label": label,
        "t0": time.perf_counter(),
        "marks": [],       # [(阶段名, 毫秒)]
    }


def mark(stage, ms=None):
    """记录一个阶段耗时。

    @param stage 阶段名（如 db.connect / inbox.read / tool.exec）
    @param ms    耗时毫秒；不传则按「距上次标记」自动计算
    """
    tr = getattr(g, "_trace", None)
    if tr is None:
        return
    now = time.perf_counter()
    if ms is None:
        # 距上一次标记（或起点）的间隔：用于「连续打点」式的阶段测量
        last = tr["t0"] + sum(m for _, m in tr["marks"]) / 1000.0
        ms = (now - last) * 1000.0
    tr["marks"].append((str(stage), round(float(ms), 1)))


def finish(extra=""):
    """结束追踪：总耗时超阈值时打一条含各阶段的 WARN，否则 DEBUG。

    @param extra 附加说明（如状态码、消息条数），拼在日志末尾
    """
    tr = getattr(g, "_trace", None)
    if tr is None:
        return
    total = (time.perf_counter() - tr["t0"]) * 1000.0
    # 阶段耗时按降序拼接：最耗时的排最前，便于一眼定位瓶颈
    parts = " ".join("%s=%.1fms" % (k, v)
                     for k, v in sorted(tr["marks"], key=lambda x: -x[1]))
    line = "[trace] %s 总=%.1fms %s%s" % (
        tr["label"], total, parts, (" " + extra) if extra else "")
    if total >= _SLOW_TOTAL_MS:
        app_log.warn(line)
    else:
        app_log.debug(line)
    g._trace = None
