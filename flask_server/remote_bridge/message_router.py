"""远程桥接 —— 消息分流与推送

职责：
1. 处理来自抽屉的上报：拿全量消息切片与「已推送集合」比对，取差集
2. 按三类（用户 / 工具 / AI）给消息打标签
3. 过滤 QQ 来源，避免把用户自己发的话复读回去
4. 按推送开关与粒度规则，组装文本并通过被动回复窗口发到 QQ

消息 id 与消息树的口径一致：直接复用抽屉传来的消息 id（内容指纹）。
"""
import threading
import time

from . import bridge_store
# 消息解析与块文本组装已抽到独立模块 message_parse.py；
# 此处按原名导入，保持本模块内既有调用不变。
from .message_parse import (
    _parse_envelope, _has_qq_source, _tool_result_of, _classify, _blocks_to_text,
)

# 被动回复窗口时长（秒）：官方为 60 分钟
WINDOW_SECONDS = 60 * 60

# 三类消息的展示前缀
PREFIX = {
    "user": "👤 用户",
    "tool": "🛠 工具",
    "ai": "🤖 AI",
}

_lock = threading.Lock()

# 推送串行锁：handle_report 的「读已推集合 → 逐条推送 → 写回」
# 必须整体串行，否则多个上报并发时会：读到同一份集合 → 同一条被推两次（重复）、
# 推送顺序互相穿插（乱序）。用独立锁，不能复用 _lock——
# 推送内部会调 next_seq，后者也要 _lock，复用会自锁死。
_push_lock = threading.Lock()

# 当前活跃的被动回复窗口：{ openid: {"msg_id": ..., "expire": 时间戳} }
_windows = {}

# 最近一个发来消息的 openid。
# 抽屉上报时并不知道 openid（那是 QQ 侧的概念），因此回退用它——
# 单用户场景下，「最近跟我说话的人」就是推送目标。
_last_openid = ""




def _remember_window(openid, msg_id):
    """记录 / 刷新某用户的被动回复窗口。

    seq 绑定在 msg_id 上：同一 msg_id 内必须唯一且递增，
    换新 msg_id（用户又发了消息）时归零重新计数。
    """
    global _last_openid
    with _lock:
        _last_openid = openid
        old = _windows.get(openid)
        # 同一 msg_id 保留既有计数继续递增；换了 msg_id 则从 0 重新开始
        seq = 0
        if old and old.get("msg_id") == msg_id:
            seq = old.get("seq", 0)
        _windows[openid] = {
            "msg_id": msg_id,
            "expire": time.time() + WINDOW_SECONDS,
            "seq": seq,
        }


def get_last_openid():
    """取最近发来消息的 openid。

    抽屉上报工具结果时并不知道 openid（那是 QQ 侧的概念），
    需要推 QQ 图片时用它作推送目标的回退。
    """
    return _last_openid


def get_window(openid):
    """取某用户当前的窗口信息；无或已过期返回 None。"""
    with _lock:
        w = _windows.get(openid)
        if not w:
            return None
        if time.time() >= w["expire"]:
            return None
        return dict(w)


def next_seq(openid):
    """取当前窗口下一个可用的 msg_seq，并自增。

    QQ 规定 msg_seq 在同一 msg_id 内必须唯一：重复的 (msg_id, msg_seq)
    会被判为「消息被去重」（错误码 40054005）而丢弃。
    因此所有发送路径都必须共用这一个计数器，不能各自从 1 重数。
    返回 (msg_id, seq)；窗口不存在时返回 (None, 0)。
    """
    with _lock:
        w = _windows.get(openid)
        if not w or time.time() >= w["expire"]:
            return None, 0
        w["seq"] = w.get("seq", 0) + 1
        return w["msg_id"], w["seq"]


def note_incoming(openid, msg_id):
    """收到用户新消息时调用：刷新窗口（用户发消息即续期）。"""
    _remember_window(openid, msg_id)


def push_text(qq_client, openid, text, markdown=False):
    """把一段文本推送到 QQ。使用当前窗口的最新 msg_id 作被动回复。

    msg_seq 由 next_seq 统一分配：同一 msg_id 内唯一递增，
    避免 (msg_id, msg_seq) 重复导致消息被 QQ 判重丢弃。
    markdown 为真时按 Markdown 消息发送（msg_type=2），否则按纯文本。
    """
    msg_id, seq = next_seq(openid)
    if not msg_id:
        # 窗口关闭：无处可推，静默丢弃（设计上等待用户下次发消息唤醒）
        print("[bridge][router] 窗口已关闭，暂不推送")
        return False
    ok, data = qq_client.send_c2c(openid, text, msg_id=msg_id, msg_seq=seq, markdown=markdown)
    if not ok:
        print("[bridge][router] 推送失败：", data)
    return ok


def push_image(qq_client, openid, path):
    """把一张本地图片推送到 QQ（与 /sp 指令同路）。

    使用当前被动回复窗口；窗口关闭时静默跳过（等用户下次发消息再唤醒），
    与文本推送的策略保持一致。
    @param qq_client QQClient 实例
    @param openid 目标用户
    @param path 本地图片绝对路径
    @returns 是否发送成功
    """
    if not qq_client or not openid or not path:
        return False
    msg_id, seq = next_seq(openid)
    if not msg_id:
        print("[bridge][router] 窗口已关闭，暂不推送图片")
        return False
    ok, data = qq_client.send_c2c_image(openid, path, msg_id=msg_id, msg_seq=seq)
    if not ok:
        print("[bridge][router] 推送图片失败：", data)
    return ok


def _should_push(m, push):
    """判断一条消息是否应当推送：类型开关打开，且不是 QQ 自己发来的。"""
    kind = _classify(m)
    # 推送开关：三类（user / tool / ai）各自控制
    if not push.get(kind, True):
        return False
    # 去重：QQ 自己发来的消息不回推，避免把用户刚说的话复读回去
    return not _has_qq_source(m)


def _push_one(qq_client, openid, m, push):
    """尝试推送一条消息到 QQ，返回状态字符串。

    三种结果，供调用方决定是否记账：
      'skip' —— 本就不该推（类型开关关闭 / QQ 自己发的 / 内容为空）：
                记入已推集合，之后不再重复评估。
      'sent' —— 推送成功：记入已推集合。
      'fail' —— 尝试推送但失败（窗口关闭 / 网络错误）：**不记账**，
                留待下轮上报重试，避免消息被永久漏掉。
    """
    if not _should_push(m, push):
        return 'skip'
    # 节点上的 md 字段是 /md 采集来的 Markdown 原文，有它说明这条回复带格式。
    # 有 md → 走 Markdown 通道（msg_type=2），QQ 端才会渲染标题、加粗等语法；
    # 没有（未采集 / 非 AI 消息 / 采集失败）→ 退回 blocks 拼的纯文本，走文本通道。
    kind = _classify(m)
    # 工具结果消息（bridge-chat-res）：正文是一段 JSON，
    # 包进代码块并按 Markdown 发送，QQ 端才会渲染成等宽格式。
    # 直接用解析出的对象反序列化，不经 _blocks_to_text：
    # 后者对代码块会自行加围栏，再包一层会形成嵌套围栏、Markdown 渲染破损。
    tr = _tool_result_of(m)
    if tr is not None:
        import json
        text = json.dumps(tr, ensure_ascii=False, indent=2)
        body = "%s\n```json\n%s\n```" % (PREFIX.get(kind, kind), text)
        return 'sent' if push_text(qq_client, openid, body, markdown=True) else 'fail'
    raw_md = str(m.get("md") or "").strip()
    is_markdown = bool(raw_md)
    text = raw_md or _blocks_to_text(m, push.get("thinking", False))
    if not text:
        return 'skip'
    body = "%s\n%s" % (PREFIX.get(kind, kind), text)
    # seq 由 push_text 内部统一分配，不能在此自行编号：
    # 各轮上报都从 1 重数会导致 (msg_id, msg_seq) 重复、消息被 QQ 丢弃
    return 'sent' if push_text(qq_client, openid, body, markdown=is_markdown) else 'fail'


def _resolve_openid(payload):
    """确定推送目标 openid：优先用上报值，回退到「最近发消息的人」。"""
    return payload.get("openid") or _last_openid or ""


def _push_card_result(qq_client, openid, card, push):
    """推送一条工具卡片结果到 QQ。

    只处理截图类结果（发图片，与 /sp 同路）。文本结果不在此推送：
    它经「回传网页 AI → 成为一条消息 → 镜像抓取」本来就能到 QQ，
    在此再推会重复。
    受 tool 推送开关控制，与正文消息一致。
    @param qq_client QQClient 实例
    @param openid 目标用户
    @param card 卡片结果 {id, tool, status, path}
    @param push 推送开关字典
    @returns 是否发送成功
    """
    if not push.get("tool", True):
        return False
    img_path = card.get("path") or ""
    if not img_path:
        return False
    return push_image(qq_client, openid, img_path)


def handle_report(qq_client, payload):
    """处理抽屉上报：diff 出新增消息并推送。

    @param qq_client QQClient 实例
    @param payload   上报体：{ conversationId, messages:[{id, role, blocks}], openid }
    @returns 本次推送的消息条数
    """
    if not qq_client:
        return 0
    conv_id = payload.get("conversationId") or "__default__"
    openid = _resolve_openid(payload)
    messages = payload.get("messages") or []
    if not openid or not messages:
        return 0

    push = bridge_store.get_config().get("push") or {}
    # 整段「读已推集合 → 逐条推送 → 写回」串行执行：
    # 否则多个上报并发会读到同一份集合，导致同一条被推两次（重复）、顺序穿插（乱序）。
    with _push_lock:
        pushed = bridge_store.get_pushed_set(conv_id)
        sent = 0
        seen_keys = []

        for m in messages:
            mid = m.get("id") or ""
            # 1) 正文推送：按消息 id 去重。
            #    工具结果是在 AI 消息推过之后才产生的，故正文与结果必须各自去重，
            #    否则「消息已推过」会把后来的结果一并挡掉。
            if mid and mid not in pushed:
                status = _push_one(qq_client, openid, m, push)
                if status == 'sent':
                    sent += 1
                # 失败不记账：留待下轮重试，避免消息被永久漏掉
                if status in ('sent', 'skip'):
                    seen_keys.append(mid)
            # 2) 卡片结果推送：按「消息id#卡片id」去重，与正文互不影响。
            for card in (m.get("cardResults") or []):
                cid = card.get("id") or ""
                if not cid:
                    continue
                ckey = (mid + "#" + cid) if mid else cid
                if ckey in pushed or ckey in seen_keys:
                    continue
                if _push_card_result(qq_client, openid, card, push):
                    sent += 1
                    seen_keys.append(ckey)
                # 图片推送失败不记账，同样留待重试

        # 只登记本轮「成功或本就不该推」的 key；失败的不写，下轮会再评估
        bridge_store.mark_pushed(conv_id, seen_keys)
        return sent
