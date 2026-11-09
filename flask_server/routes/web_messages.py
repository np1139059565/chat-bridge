"""网页版 —— 收件箱消息的拉取实现

从 routes/web.py 抽出（2026-11-09：该文件因站点过滤分支达到行数上限）。
三个分支共用同一套站点过滤语义，集中在此便于对照维护。
"""
from flask import jsonify, request

from web_bridge import web_inbox


def messages_before(before, site):
    """向上翻历史：返回比指定 seq 更早的一批消息。

    @param before 已渲染的最早一条的 seq
    @param site   站点过滤（None=不过滤）
    @returns Flask 响应
    """
    try:
        blimit = int(request.args.get("limit", "50"))
    except ValueError:
        blimit = 50
    # 单批上限 100：翻历史是交互式操作，一次给太多会重新撑大页面
    data = web_inbox.before_seq(before, max(1, min(blimit, 100)), site)
    return jsonify(success=True, **data)


def messages_cursor(site):
    """按游标拉取：history=1 走首屏铺历史，否则走增量。

    @param site 站点过滤（None=不过滤）
    @returns Flask 响应
    """
    from web_bridge import web_poll_log
    web_poll_log.log_poll_start()
    import time as _t
    _t0 = _t.perf_counter()
    if request.args.get("history") == "1":
        # 首次铺屏只给最近 10 条：首屏渲染越轻，手机端越快看到内容。
        # 其余历史靠滑到底部懒加载（before_seq 分批取），避免一次渲染过多撑爆手机内存。
        try:
            hlimit = int(request.args.get("limit", "10"))
        except ValueError:
            hlimit = 10
        data = web_inbox.recent(max(1, min(hlimit, 100)), site)
    else:
        cursor = request.args.get("cursor", "0")
        try:
            limit = int(request.args.get("limit", "200"))
        except ValueError:
            limit = 200
        data = web_inbox.list_since(cursor, limit, site)
    # 读收件箱（含等锁 + 读缓存/解析）耗时：轮询卡顿最常见的嫌疑点
    web_poll_log.log_poll_done(request.args.get("cursor", "0"), data,
                               (_t.perf_counter() - _t0) * 1000.0)
    return jsonify(success=True, **data)
