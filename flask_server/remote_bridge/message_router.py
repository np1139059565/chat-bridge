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

from . import bridge_store, bridge_log, message_images


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][router]", *args)
# 消息解析与块文本组装已抽到独立模块 message_parse.py；
# 此处按原名导入，保持本模块内既有调用不变。
from .message_parse import (
    _parse_envelope, _has_qq_source, _tool_result_of, _classify, _blocks_to_text,
    _thinking_text_of,
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

# 推送串行锁（按会话隔离）：handle_report 的「读已推集合 → 逐条推送 → 写回」
# 对同一会话必须整体串行，否则多个上报并发时会：读到同一份集合 → 同一条被推
# 两次（重复）、推送顺序互相穿插（乱序）。用独立锁，不能复用 _lock——
# 推送内部会调 next_seq，后者也要 _lock，复用会自锁死。
#
# 之所以「按会话」而非「全局一把」：锁内包含 QQ 网络推送，若全局共用，
# 一个慢会话会长时间持有该锁，把其它所有会话的推送一并拖住（串行排队）。
# 按会话分锁后，不同会话互不阻塞，同一会话仍保持串行。
_conv_locks = {}                      # conversationId -> threading.Lock
_conv_locks_lock = threading.Lock()   # 保护 _conv_locks 字典本身的增删


def _lock_for(conv_id):
    """取某会话的推送锁；不存在则创建。

    返回的锁只保证「同一会话内」的推送串行，不同会话各用各的锁，互不阻塞。
    @param conv_id 会话标识
    @returns 该会话的 threading.Lock
    """
    with _conv_locks_lock:
        lock = _conv_locks.get(conv_id)
        if lock is None:
            lock = threading.Lock()
            _conv_locks[conv_id] = lock
        return lock

# 单次上报最多处理的消息条数取自全项目统一来源（app_limits）：长时间不开 QQ 后
# 重开，抽屉会一次性上报全量切片（可能几百条）。若全量逐条合成语音 + 推送，
# 会在请求线程里串行跑几百次网络调用，把接口拖死。故超过此上限时只处理最新的一批，
# 更旧的直接跳过——符合「堆积很多时只补最后几条即可」。
from app_limits import MAX_PUSH_PER_REPORT

# 当前活跃的被动回复窗口：{ openid: {"msg_id": ..., "expire": 时间戳} }
_windows = {}

# 最近一次上报切片缓存：{ conv_id: payload }。
# 用途：把「窗口更新」与「消息推送」连起来——用户发消息续期后重放一次，
# 补推此前因窗口关闭而滞后的消息（见 note_incoming）。
_last_report = {}

# 最近一次上报用的 QQClient 引用：重放时复用（note_incoming 拿不到 client）。
_last_client = None

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
    """收到用户新消息时调用：刷新窗口，并补推此前的滞后消息。

    关键：窗口更新与消息推送本是解耦的——推送只由抽屉上报触发。
    因此用户发消息（尤其是指令）虽续了期，却不会自动补推积压消息，
    表现为「发了新问题，上一条才姗姗来迟」。这里在续期后主动重放
    最近一次上报切片：此时窗口已开，去重复用已推集合，滞后者得以补推。
    """
    _remember_window(openid, msg_id)
    _replay_last_report()


def _replay_last_report():
    """续期后重放最近一次上报切片，补推滞后消息。

    放后台线程执行：重放内部会发 HTTP 推送，若同步跑在 WebSocket 回调线程里，
    会阻塞心跳、甚至触发断连（与语音处理同理）。
    只读缓存、复用现有去重：已在「已推集合」里的不会重复推送；
    异常一律吞掉——补推是尽力而为，不能影响消息接收主流程。
    """
    client = _last_client
    if not client:
        return

    def _worker():
        # 复制一份：重放期间可能有新上报写入缓存，边遍历边改会出问题
        for conv_id, payload in list(_last_report.items()):
            try:
                handle_report(client, payload)
                log("续期后重放补推", conv_id)
            except Exception as e:
                log("续期后重放失败（不影响接收）：", e)

    threading.Thread(target=_worker, daemon=True).start()


def push_text(qq_client, openid, text, markdown=False):
    """把一段文本推送到 QQ。使用当前窗口的最新 msg_id 作被动回复。

    msg_seq 由 next_seq 统一分配：同一 msg_id 内唯一递增，
    避免 (msg_id, msg_seq) 重复导致消息被 QQ 判重丢弃。
    markdown 为真时按 Markdown 消息发送（msg_type=2），否则按纯文本。
    """
    msg_id, seq = next_seq(openid)
    if not msg_id:
        # 窗口关闭：无处可推，静默丢弃（设计上等待用户下次发消息唤醒）
        log("窗口已关闭，暂不推送")
        return False
    ok, data = qq_client.send_c2c(openid, text, msg_id=msg_id, msg_seq=seq, markdown=markdown)
    if not ok:
        log("推送失败：", data)
    return ok



# 出向语音（提取语音文本 / 合成 / 推送）已抽到 message_voice.py，
# 使本文件保持在行数上限内；此处按原名导入，保持既有调用不变。
from .message_voice import (
    extract_voice_from_blocks as _extract_voice_from_blocks,
    push_voice,
    synthesize_voice as _synthesize_voice,
)


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
        log("窗口已关闭，暂不推送图片")
        return False
    ok, data = qq_client.send_c2c_image(openid, path, msg_id=msg_id, msg_seq=seq)
    if not ok:
        log("推送图片失败：", data)
    return ok


def _should_push(m, push):
    """判断一条消息是否应当推送：类型开关打开，且不是 QQ 自己发来的。"""
    kind = _classify(m)
    # 推送开关：三类（user / tool / ai）各自控制
    if not push.get(kind, True):
        return False
    # 去重：QQ 自己发来的消息不回推，避免把用户刚说的话复读回去
    return not _has_qq_source(m)


def _push_one(qq_client, openid, m, push, voice_paths=None):
    """尝试推送一条消息到 QQ，返回状态字符串。

    三种结果，供调用方决定是否记账：
      'skip' —— 本就不该推（类型开关关闭 / QQ 自己发的 / 内容为空）：
                记入已推集合，之后不再重复评估。
      'sent' —— 推送成功：记入已推集合。
      'fail' —— 尝试推送但失败（窗口关闭 / 网络错误）：**不记账**，
                留待下轮上报重试，避免消息被永久漏掉。

    @param voice_paths 预合成好的语音路径映射 {消息id: 音频路径}。
        合成由调用方在会话推送锁之外预先完成——合成是网络调用，
        绝不能在锁内执行（否则在线服务一卡，锁被占死、线程堆满、
        服务器拒绝新连接，必须重启才能恢复）。本函数只负责在正文
        推送成功后按序推送对应语音。
    """
    if not _should_push(m, push):
        return 'skip'
    # 正文组装统一交给 outbound.build_body：QQ 与网页共用同一套规则，
    # 避免两边各写一份导致「网页版没有思考」这类改造不彻底的问题。
    from .outbound import build_body
    built = build_body(m, push)
    if built.get("skip"):
        return 'skip'
    kind = built.get("kind") or _classify(m)
    text = built.get("text") or ""
    body = "%s\n%s" % (PREFIX.get(kind, kind), text)
    # seq 由 push_text 内部统一分配，不能在此自行编号：
    # 各轮上报都从 1 重数会导致 (msg_id, msg_seq) 重复、消息被 QQ 丢弃
    ok = push_text(qq_client, openid, body, markdown=bool(built.get("markdown")))
    # 正文推送成功后，紧跟着推这条消息的语音（音频已由调用方在锁外预合成，
    # 经 voice_paths 传入）。放在正文之后同一轮里推，恢复「文本→语音」顺序，
    # 避免一批消息的语音全部被挤到末尾。
    if kind == "ai" and not built.get("is_tool_result"):
        _push_voice_after(qq_client, openid, m, voice_paths, ok)
    return 'sent' if ok else 'fail'


def _push_voice_after(qq_client, openid, m, voice_paths, text_ok):
    """正文推送后，紧跟着推这条消息的语音（保持「文本→语音」顺序）。

    正文推成功才推语音；推完即删临时音频。正文失败时不推，文件也删掉——
    下轮重试会重新合成，不留垃圾。
    @param qq_client   QQClient 实例
    @param openid      收件人
    @param m           消息对象
    @param voice_paths 预合成的 {消息id: 音频路径}
    @param text_ok     正文是否推送成功
    """
    path = (voice_paths or {}).get(m.get("id") or "")
    if not path:
        return
    if text_ok:
        try:
            push_voice(qq_client, openid, path)
        except Exception as e:
            log("语音推送失败（不影响主流程）：", e)
    _remove_voice_file(path)


def _remove_voice_file(path):
    """删除预合成的临时语音文件（推完或正文失败后调用），失败静默。"""
    if not path:
        return
    try:
        import os
        os.remove(path)
    except OSError:
        pass


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


def _push_images_block(qq_client, openid, m, push, pushed, seen_keys):
    """推送一条消息里的图片块并记账，返回成功张数。

    从 handle_report 内层循环抽出，避免嵌套过深；seen_keys 就地追加。
    """
    mid = m.get("id") or ""
    ikey = (mid + "#img") if mid else ""
    if ikey and (ikey in pushed or ikey in seen_keys):
        return 0
    n = message_images.push_message_images(qq_client, openid, m, push, push_image)
    if n > 0 and ikey:
        seen_keys.append(ikey)
    return n


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
    # 合并上次推送失败的消息：它们可能已滚出可见区、不再出现在切片里，
    # 靠这份缓存获得重试机会（成功 / 跳过后自动移出，见本函数末尾 set_pending）。
    messages = bridge_store.merge_pending(conv_id, messages)
    # 条数上限：长时间不开 QQ 后重开，切片可能堆积几百条。只取最新的一批处理，
    # 更旧的直接丢弃——它们多半已被后续消息覆盖，用户要的也是「最后几条」。
    # 这一步在合成/推送之前，确保后续的网络调用次数被硬性封顶，接口不会被拖死。
    if len(messages) > MAX_PUSH_PER_REPORT:
        messages = messages[-MAX_PUSH_PER_REPORT:]
    # 缓存最近一次切片与客户端：用户续期窗口后据此重放，补推滞后消息。
    # 只存引用，不深拷贝：切片可能很大，且重放时只读。
    global _last_client
    _last_client = qq_client
    _last_report[conv_id] = payload

    push = bridge_store.get_config().get("push") or {}
    # 第一步（锁外）：预合成语音。
    # 合成是网络调用、可能很慢，绝不能在本会话推送锁内做——否则该会话一卡
    # 就会长时间占用其推送锁、上报线程堆满、服务器拒绝连接（必须重启才恢复）。
    # 在锁外先把本轮要推的 AI 语音统统合成好，得到 {消息id: 音频路径}，
    # 锁内只按序推送，既保住「文本→语音」顺序，又不占锁。
    # 推送编排已抽到 message_flow 模块，此处延迟导入避免循环依赖。
    from . import message_flow
    voice_paths = message_flow.presynth_voice(messages, push)

    # 第二步（会话锁内）：整段「读已推集合 → 逐条推送 → 写回」对同一会话串行执行：
    # 否则同会话多个上报并发会读到同一份集合，导致同一条被推两次（重复）、顺序穿插（乱序）。
    # 按会话分锁：不同会话各用各的锁，一个慢会话不会拖住其它会话的推送。
    with _lock_for(conv_id):
        sent = message_flow.push_batch_locked(qq_client, openid, conv_id, messages, push, voice_paths)

    # 兜底清理：预合成了语音、但正文已推过（未进 _push_one）的，其音频没人删，
    # 在此统一清掉，避免临时文件堆积。
    for _mid, _p in voice_paths.items():
        _remove_voice_file(_p)
    return sent

