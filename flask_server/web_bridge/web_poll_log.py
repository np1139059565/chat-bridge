"""网页版 —— 轮询与发消息的可观测性辅助

职责：为网页端两条最关键的链路（拉消息、发消息）提供统一的日志与阶段打点，
从 routes/web.py 抽出，使后者保持在仓库行数上限内。

为什么这两条链路要单独记日志：
  网页版跑在手机浏览器上，用户看不到控制台。前端上报的日志只能在
  主线程还能跑时发出；一旦请求本身卡住，后端日志才是唯一证据。
  轮询与发消息正是「界面卡住」「已连接却发不出去」的直接现场。

设计：全部函数都做异常兜底——诊断能力自身绝不能成为新的故障点。

依赖：time、app_log、req_trace
"""
import time

import app_log


def _mark(stage, ms):
    """安全打点：req_trace 不可用或调用出错时静默忽略。

    @param stage 阶段名
    @param ms    耗时毫秒
    """
    try:
        import req_trace
        req_trace.mark(stage, ms)
    except Exception:
        pass


def log_poll_start():
    """记录「开始读取收件箱」这一时点。

    目的是把「参数解析」与「读收件箱」两段耗时在追踪里分开。
    """
    _mark("messages.parse_args", None)


def log_poll_done(cursor, data, ms):
    """记录一次轮询的结果。

    字段选择的理由：
      - cursor：这次是从哪个游标开始拉的；
      - 返回条数：区分「没新消息」与「有消息但没取到」；
      - 新游标：确认游标是否推进（不推进会导致重复拉同一批）；
      - 耗时：判断是否变慢。
    @param cursor 本次请求带的游标
    @param data   收件箱返回的 {seq, messages}
    @param ms     读取耗时（毫秒）
    """
    _mark("messages.read_inbox", ms)
    try:
        app_log.info("[web][poll]", "cursor=%s 返回=%d 条 新游标=%s 耗时=%.1fms"
                     % (cursor, len((data or {}).get("messages") or []),
                        (data or {}).get("seq"), ms))
    except Exception:
        pass


def new_send_timer():
    """创建一次发消息的分段计时器。

    用法：t = new_send_timer()；投卡片后调 t.mark_card()，
    写收件箱后调 t.mark_inbox(长度)。
    这样做的原因：发消息分「投卡片」与「写收件箱」两步，
    二者失败原因完全不同，必须分开计时才能定位。
    @returns 计时器对象
    """
    return SendTimer(time.perf_counter())


class SendTimer:
    """发消息分段计时器：记录投卡片与写收件箱两段耗时。"""

    def __init__(self, t0):
        """@param t0 起始时间（time.perf_counter）"""
        self.t0 = t0
        self.t1 = None

    def mark_card(self):
        """标记「投卡片」阶段结束。"""
        self.t1 = time.perf_counter()
        _mark("send.ingest_card", (self.t1 - self.t0) * 1000.0)

    def mark_inbox(self, text_len):
        """标记「写收件箱」阶段结束，并输出一行汇总日志。

        @param text_len 消息正文长度（判断是否因超长文本拖慢写入）
        """
        t2 = time.perf_counter()
        card_ms = ((self.t1 - self.t0) * 1000.0) if self.t1 else 0.0
        inbox_ms = (t2 - (self.t1 or self.t0)) * 1000.0
        _mark("send.inbox_append", inbox_ms)
        try:
            app_log.info("[web][send]", "投卡片=%.1fms 写收件箱=%.1fms 长度=%d"
                         % (card_ms, inbox_ms, text_len))
        except Exception:
            pass
