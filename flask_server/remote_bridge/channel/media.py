"""远程桥接 —— 出向媒体的公共骨架

各通道推媒体的流程是同一个：

    从这批消息里收集图片 / 文件 / 语音
    → 逐件交给通道自己的发送函数
    → 统计成功条数

只有「怎么发」是通道差异（企微要 media_id、微信要 data URL、QQ 走窗口），
「收什么、发几件、怎么计数」完全共通。本模块固定后者，前者由调用方
以 send_fn 注入。

语音的特殊之处：只在 AI 消息上推。用户消息与工具消息没有可朗读的正文，
给它们合成语音既浪费额度，也让用户莫名其妙听到自己刚说的话。
"""
from ..message_parse import _classify
from ..wecom_media_collect import (
    collect_files, collect_images, collect_voice,
)


def push_collected(items, push, voice_map, send_fn):
    """收集这批消息里的媒体并逐件发送。

    @param items     本轮待推消息列表
    @param push      推送开关（读 push["voice"] 决定是否推语音）
    @param voice_map 预合成的 {消息id: 音频路径}
    @param send_fn   通道的发送函数，签名 (path, kind) -> bool，
                     kind 取 image / file / voice
    @returns 成功发送的媒体条数
    """
    # 第一步：把三类媒体从消息里收集出来
    images, files, voices = _collect_all(items, push, voice_map)
    # 第二步：按固定顺序逐件发送并计数
    return _send_all(send_fn, images, files, voices)


def _collect_all(items, push, voice_map):
    """把一批消息里的三类媒体分别收集出来。

    @param items     待推消息列表
    @param push      推送开关
    @param voice_map 预合成的音频路径映射
    @returns (图片路径列表, 文件路径列表, 语音路径列表)
    """
    images, files, voices = [], [], []
    for m in items:
        # 图片与文件：消息里有就收，与消息类别无关
        images.extend(collect_images(m))
        files.extend(collect_files(m))
        # 语音单独处理：受开关与消息类别双重约束
        vpath = _voice_of(m, push, voice_map)
        if vpath:
            voices.append(vpath)
    return images, files, voices


def _voice_of(m, push, voice_map):
    """取一条消息要推的语音路径；不该推时返回空串。

    两个条件同时满足才推：语音开关打开、消息是 AI 回复。
    用户与工具消息没有可朗读的正文，推了只会让人听到自己刚说的话。

    @param m         消息对象
    @param push      推送开关
    @param voice_map 预合成的音频路径映射
    @returns 音频路径；不推时为空串
    """
    # 开关关闭：整条通道不推语音
    if not push.get("voice"):
        return ""
    vpath, vtext = collect_voice(m, voice_map)
    # 合成失败（无路径或无可读文字）直接跳过
    if not (vpath and vtext):
        return ""
    # 只有 AI 消息才值得朗读
    return vpath if _classify(m) == "ai" else ""


def _send_all(send_fn, images, files, voices):
    """按 图片 → 文件 → 语音 的顺序逐件发送并计数。

    顺序固定：用户先看到画面，再拿到附件，最后听语音。

    @param send_fn 通道发送函数
    @param images  图片路径列表
    @param files   文件路径列表
    @param voices  语音路径列表
    @returns 成功发送的件数
    """
    sent = 0
    for kind, paths in (("image", images), ("file", files), ("voice", voices)):
        for path in paths:
            if send_fn(path, kind):
                sent += 1
    return sent
