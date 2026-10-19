"""远程桥接 —— 上报推送流程

职责：承载 handle_report 的推送编排逻辑（预合成语音、锁内逐条推送、
正文/图片/卡片分发、语音后置推送），使 message_router 保持精简。

为何独立成模块：
- message_router 承担上报入口、窗口状态、seq 分配等，职责已多；
- 推送编排是纯流程控制，与状态管理分离后两边都更清晰。

依赖说明（避免循环导入）：
- 本模块顶层只依赖通用模块（bridge_store、bridge_log）；
- 对 message_router 内的推送原语（_push_one / _push_images_block /
  _push_card_result / _synthesize_voice / _should_push / _remove_voice_file /
  push_voice），一律在函数内延迟导入，避免与 message_router 形成顶层循环。
"""
from collections import namedtuple

from . import bridge_store
from .bridge_log import write as _blog

# 推送上下文：把「目标客户端 + 收件人 + 推送开关」三者打包传递，
# 既减少函数参数个数（质量门禁限制 6 个），又让调用处更简洁。
PushCtx = namedtuple("PushCtx", ["qq_client", "openid", "push"])


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    _blog("[bridge][router]", *args)


def presynth_voice(messages, push):
    """取本轮可用的语音路径：只查缓存，不做任何合成。

    设计要点——「文字优先」：合成一条语音要一秒以上，若在推文字前做完，
    用户要等整批语音合成完毕才看到第一条回音。故此处只做零成本的缓存查找，
    命中的直接随正文一起推；未命中的留到文字全部推完后，由
    postsynth_and_push_voice 并发合成再补推。

    @param messages 本轮消息列表
    @param push     推送开关字典
    @returns {消息id: 音频路径}；未开语音或无缓存命中时为空字典
    """
    from . import voice_cache
    voice_paths = {}
    if not push.get("voice"):
        return voice_paths
    for m in messages:
        mid = m.get("id") or ""
        if not mid or not _should_synth(m, push):
            continue
        text = _voice_text_of(m)
        cached = voice_cache.lookup(text) if text else ""
        if cached:
            voice_paths[mid] = cached
    return voice_paths


def postsynth_and_push_voice(qq_client, openid, messages, push, voice_paths):
    """文字推完后补语音：并发合成未命中的，逐条推给 QQ。

    在会话推送锁之外调用：语音推送只是补充，不该占住正文推送锁。
    合成按「文本内容哈希」入缓存，网页点播用过的音频直接复用。

    @param qq_client   QQClient 实例
    @param openid      收件人
    @param messages    本轮消息列表
    @param push        推送开关字典
    @param voice_paths 已有的 {消息id: 音频路径}（就地补充，含缓存命中项）
    """
    from concurrent.futures import ThreadPoolExecutor
    from app_limits import MAX_CONCURRENT_SYNTH
    from . import voice_cache
    if not push.get("voice"):
        return
    # 只补「要合成但还没有路径」的消息
    pending = []
    for m in messages:
        mid = m.get("id") or ""
        if not mid or mid in voice_paths or not _should_synth(m, push):
            continue
        text = _voice_text_of(m)
        if text:
            pending.append((mid, text))
    if not pending:
        return

    def _one(item):
        mid, text = item
        try:
            from . import message_router as mr
            path = mr._synthesize_voice_text(text)
            return mid, (voice_cache.store(text, path) if path else "")
        except Exception as e:
            log("语音合成失败（不影响主流程）：", e)
            return mid, ""

    # 并发合成：串行时十几条会把补推拖后十几秒；上限取自 app_limits
    results = []
    try:
        with ThreadPoolExecutor(max_workers=max(1, MAX_CONCURRENT_SYNTH)) as pool:
            results = list(pool.map(_one, pending))
    except Exception as e:
        log("语音并发合成异常（不影响主流程）：", e)
    # 按原顺序逐条推语音，保持「文本→语音」的对应关系
    for mid, path in results:
        if not path:
            continue
        try:
            from .message_voice import push_voice
            push_voice(qq_client, openid, path)
        except Exception as e:
            log("语音推送失败（不影响主流程）：", e)


def _voice_text_of(m):
    """取一条消息的朗读文本（供缓存键与合成使用）。

    @param m 消息对象
    @returns 朗读文本；无语音返回空串
    """
    try:
        from .message_voice import extract_voice_from_blocks
        return extract_voice_from_blocks(m) or ""
    except Exception:
        return ""


def _should_synth(m, push):
    """判断一条消息是否该预合成语音：可推送、且是 AI 正文（非工具结果）。

    @param m    消息对象
    @param push 推送开关字典
    @returns 需要合成为 True
    """
    from . import message_router as mr
    if not mr._should_push(m, push):
        return False
    try:
        from .outbound import build_body
        built = build_body(m, push)
        return built.get("kind") == "ai" and not built.get("is_tool_result")
    except Exception:
        return False


def push_batch_locked(qq_client, openid, conv_id, messages, push, voice_paths):
    """在会话锁内逐条推送，返回本次推送条数。

    整段「读已推集合 → 逐条推送 → 写回」须对同一会话串行，否则并发上报会重复或乱序。
    调用方必须已持有对应会话的推送锁。
    @returns 本次推送条数
    """
    ctx = PushCtx(qq_client, openid, push)
    pushed = bridge_store.get_pushed_set(conv_id)
    sent = 0
    seen_keys = []
    # 本轮推送失败的消息：结束后写入待推缓存，供下次上报优先重试。
    failed = []
    for m in messages:
        # 正文与图片：按消息 id（及 #img 后缀）各自去重
        one_sent, one_failed = push_message_bodies(ctx, m, pushed, seen_keys, voice_paths)
        sent += one_sent
        if one_failed:
            failed.append(m)
        # 卡片结果：按「消息id#卡片id」去重，与正文互不影响
        sent += push_message_cards(ctx, m, pushed, seen_keys)
    # 只登记本轮「成功或本就不该推」的 key；失败的不写，下轮会再评估
    bridge_store.mark_pushed(conv_id, seen_keys)
    # 回写待推缓存：本轮失败的消息挂起，下次上报优先重试
    bridge_store.set_pending(conv_id, failed)
    return sent


def push_message_bodies(ctx, m, pushed, seen_keys, voice_paths):
    """推送单条消息的正文与图片（各自去重）。

    @param ctx         推送上下文（客户端 + 收件人 + 开关）
    @param m           消息对象
    @param pushed      已推送集合
    @param seen_keys   本轮已记账 key 列表（就地追加）
    @param voice_paths 预合成的 {消息id: 音频路径}
    @returns (推送条数, 正文是否失败) 二元组
    """
    from . import message_router as mr
    mid = m.get("id") or ""
    sent = 0
    failed = False
    # 工具结果是在 AI 消息推过之后才产生的，故正文与结果必须各自去重，
    # 否则「消息已推过」会把后来的结果一并挡掉。
    if mid and mid not in pushed:
        status = mr._push_one(ctx.qq_client, ctx.openid, m, ctx.push, voice_paths)
        if status == 'sent':
            sent += 1
        # 失败不记账：留待下轮重试，避免消息被永久漏掉
        if status in ('sent', 'skip'):
            seen_keys.append(mid)
        elif status == 'fail':
            failed = True
        # 图片推送：按「消息id#img」去重，与正文各自独立
        sent += mr._push_images_block(ctx.qq_client, ctx.openid, m, ctx.push, pushed, seen_keys)
    return sent, failed


def remove_voice_file(path):
    """删除临时的语音文件（推完或正文失败后调用），失败静默。

    缓存目录里的成品一律不删：那是按文本哈希复用的一次性投入，删掉等于
    下次同一条文本又要重合成。只有临时目录里的合成产物才随推随删。

    @param path 音频路径；为空时直接返回
    """
    if not path:
        return
    try:
        import os
        import paths
        cache_dir = str(paths.VOICE_DIR / "cache")
        if os.path.abspath(os.path.dirname(path)) == os.path.abspath(cache_dir):
            return                          # 缓存成品：保留，供下次复用
        os.remove(path)
    except OSError:
        pass


def push_message_cards(ctx, m, pushed, seen_keys):
    """推送单条消息挂带的卡片结果（按「消息id#卡片id」去重）。

    @param ctx       推送上下文（客户端 + 收件人 + 开关）
    @param m         消息对象
    @param pushed    已推送集合
    @param seen_keys 本轮已记账 key 列表（就地追加）
    @returns 推送条数
    """
    from . import message_router as mr
    mid = m.get("id") or ""
    sent = 0
    for card in (m.get("cardResults") or []):
        cid = card.get("id") or ""
        if not cid:
            continue
        ckey = (mid + "#" + cid) if mid else cid
        if ckey in pushed or ckey in seen_keys:
            continue
        if mr._push_card_result(ctx.qq_client, ctx.openid, card, ctx.push):
            sent += 1
            seen_keys.append(ckey)
        # 图片推送失败不记账，同样留待重试
    return sent
