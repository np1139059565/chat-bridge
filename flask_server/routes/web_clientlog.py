"""网页版 —— 前端日志上报接口

职责：接收手机浏览器上报的前端日志，落到 client-YYYY-MM-DD.log。
从 routes/web.py 拆出，使后者保持在仓库行数上限内，也让「日志上报」
这一独立关注点集中一处。

背景：网页版跑在手机浏览器上，用户看不到控制台、无法复制日志，
故前端在关键点把日志 POST 到这里由后端落盘，供排查「页面卡住 / 断连」。
关键价值：若前端主线程被卡住，它连这条上报都发不出——后端日志会出现
整齐空档，那空档本身就是「主线程被卡住」的证据。

依赖：flask、paths、log_sink
"""
from flask import Blueprint, jsonify, request

import paths
import log_sink

bp = Blueprint("web_clientlog", __name__)

# 前端上报日志的落盘器：client-YYYY-MM-DD.log。
# 用同步 sink（非异步）：前端日志是「主线程是否被卡住」的诊断证据，
# 靠日志的整齐空档判断卡顿，故宁可写入方短暂等盘，也不丢条目。
_client_sink = log_sink.DayFileSink("client", lambda: paths.LOGS_DIR)


@bp.route("/api/web/client_log", methods=["POST", "OPTIONS"])
def web_client_log():
    """接收前端上报的日志，落到后端文件。

    请求体：单条 { tag, msg } 或一批 [{ tag, msg }, ...]（前端已改批量上报，
    把请求数从「每条一请求」降到「每秒最多一请求」，避免日志上报挤占请求线程）。
    不校验字段，能记就记；写盘用 client-YYYY-MM-DD.log，与主日志分开。
    """
    data = request.get_json(force=True, silent=True)
    # 兼容数组（批量）与对象（单条）；其它类型忽略。
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]
    else:
        items = []
    import time as _t
    now = _t.strftime("%H:%M:%S")
    for it in items:
        if not isinstance(it, dict):
            continue
        tag = str(it.get("tag") or "")
        msg = str(it.get("msg") or "")
        # 前端记录时刻（若前端已上报）：格式 HH:MM:SS.mmm。
        # 与「服务端收到时刻」一并落盘，二者不等时即可判断日志迟到：
        # 迟到说明请求发不出去（网络 / 浏览器层），恢复后集中补报。
        ct = str(it.get("t") or "")
        # 前端全局自增序号（若前端已上报）：后端据此可发现「丢号」，
        # 缺口区间即为「前端产生过但始终未送达」的日志，是定位丢失窗口的关键。
        seq = it.get("seq")
        seq_s = ("#%s" % seq) if seq is not None else ""
        # 交给公共落盘器：与其它日志共用「按天分文件 + 加锁 + 失败静默」实现，
        # 不再就地 open/write（后者未加锁，并发上报时行可能交错）。
        if ct:
            _client_sink.append("%s [client@%s]%s[%s] %s" % (now, ct, seq_s, tag, msg))
        else:
            _client_sink.append("%s [client]%s[%s] %s" % (now, seq_s, tag, msg))
    return jsonify(success=True)
