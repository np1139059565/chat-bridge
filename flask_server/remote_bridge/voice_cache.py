"""远程桥接 —— 语音成品缓存

职责：按「朗读文本」的内容哈希定位已合成的音频成品，实现跨路径复用。

为什么需要：
    网页点播语音与 QQ 推送语音原先各自合成、各自命名（out_<毫秒>.mp3 /
    out_<毫秒>_<序号>.mp3），互不知情。同一条 AI 消息在两处各合一遍，
    纯属浪费；积压补推时逐条串行合成，还把首条推送硬生生拖后十几秒。

缓存键为何用文本哈希而非消息 id：
    网页点播只知道「要朗读的文本」，拿不到 QQ 侧的消息 id；消息 id 也会
    因会话重放而变化。文本内容才是合成结果的唯一决定因素，同一段文本
    合成一次即可复用，两个入口天然共享。

存放位置：data/voice/cache/<sha1>.mp3，与推送用的临时目录分开，
    避免被「推完即删」的清理逻辑误删。
"""
import hashlib
import os

import paths


def cache_dir():
    """返回缓存目录（不存在则创建）。"""
    d = paths.VOICE_DIR / "cache"
    os.makedirs(d, exist_ok=True)
    return d


def key_of(text):
    """由朗读文本算出缓存键（SHA-1 十六进制）。

    @param text 朗读文本
    @returns 32 位以内的十六进制串；空文本返回空串
    """
    t = (text or "").strip()
    if not t:
        return ""
    return hashlib.sha1(t.encode("utf-8")).hexdigest()


def lookup(text):
    """查缓存：命中返回音频绝对路径，未命中返回空串。

    只认「文件存在且非空」——合成中途失败可能留下 0 字节残file，
    那种情况按未命中处理，交给重新合成。
    @param text 朗读文本
    @returns 音频绝对路径或空串
    """
    k = key_of(text)
    if not k:
        return ""
    p = cache_dir() / (k + ".mp3")
    try:
        if p.exists() and p.stat().st_size > 0:
            return str(p)
    except OSError:
        pass
    return ""


def store(text, src_path):
    """把一份刚合成好的音频收进缓存，返回缓存路径。

    用「先写临时名再改名」的方式落入，避免并发合成同一段文本时，
    别的线程读到写了一半的文件。
    @param text     朗读文本
    @param src_path 刚合成出的音频路径
    @returns 缓存中的音频绝对路径；失败时返回原路径
    """
    k = key_of(text)
    if not k or not src_path or not os.path.exists(src_path):
        return src_path or ""
    dst = cache_dir() / (k + ".mp3")
    if dst.exists() and dst.stat().st_size > 0:
        return str(dst)                     # 已被别的线程存好，直接复用
    tmp = cache_dir() / (k + ".mp3.tmp")
    try:
        with open(src_path, "rb") as rf, open(tmp, "wb") as wf:
            wf.write(rf.read())
        os.replace(str(tmp), str(dst))
        return str(dst)
    except OSError:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return src_path
