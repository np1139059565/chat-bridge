"""AI 工具调用镜像插件 —— 记忆系统：关键词提取

职责：从记忆文本里提取「与任务强相关」的关键词，供检索与突触关联。

流水线（对应方案 4.3）：
  1. 规则初筛：抽英文标识符 / 中文词组 / 数字，停用词过滤，词频排序。零依赖。
  2. LLM 精筛：可插拔 provider（默认关闭）。接入模型后由它挑出真正相关的词。
  3. 计划锚定校验：见 memory_search，关键词须与计划原文吻合。

设计取舍（诚实说明）：
  - 本机无中文分词库（jieba 等均未安装），故中文用 n-gram 切分 + 停用词过滤；
    精度不如专用分词，但对「任务关键词」这类偏技术术语的场景够用。
  - 后端无 LLM 客户端，故 LLM 精筛默认跳过；如需启用，注册一个 provider 即可。

依赖：re、collections
"""
import re
from collections import Counter

# 英文/数字/下划线标识符：代码术语、工具名、变量名多为此类
_RE_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}")
# 连续汉字串：用于 n-gram 切分
_RE_CJK = re.compile(r"[\u4e00-\u9fa5]+")

# 停用词表：中文虚词 + 英文常见词 + 泛化词（必须与任务强相关，故剔泛词）
_STOPWORDS = set("""
的 了 和 是 在 我 有 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 没有 看 好
自己 这 那 这个 那个 什么 怎么 为什么 可以 应该 需要 问题 优化 处理 进行 通过 由于
因为 所以 但是 而且 或者 如果 然后 现在 已经 还是 就是 只是 这样 那样 一些 这些 那些
必须 需要 应该 可以 进行 相关 强相关 任务 情况 时候 问题 地方 东西 方式 方法
the a an is are was were be been to of in on for with and or but if then this that it as at
by from we you they he she i me my your our their not no yes can should would could will
""".split())

# LLM 精筛 provider：默认 None。注册后签名 (text, candidates) -> list[str]
_llm_provider = None


def register_llm_provider(fn):
    """注册 LLM 精筛 provider（可插拔）。

    @param fn 签名 (text, candidates) -> list[str]；传 None 表示关闭
    """
    global _llm_provider
    _llm_provider = fn


def extract(text, top_k=8, use_llm=False):
    """从文本提取关键词。

    @param text 源文本
    @param top_k 返回条数上限
    @param use_llm 是否启用 LLM 精筛（需先注册 provider）
    @return 关键词列表，按相关度降序
    """
    if not text:
        return []
    candidates = _rule_candidates(text)
    if use_llm and _llm_provider is not None:
        try:
            refined = _llm_provider(text, candidates) or []
            if refined:
                return refined[:top_k]
        except Exception:
            # provider 异常时降级到规则结果，不让蒸馏中断
            pass
    return candidates[:top_k]


def _rule_candidates(text):
    """规则初筛：英文标识符 + 中文短语块，停用词过滤，按相关度降序。

    中文不切 n-gram（会产出「网页版机」这类无意义碎片），
    改为按标点与连接词把句子切成短语块，短语块才是语义单元。
    """
    scores = Counter()
    # 1) 英文标识符：直接计入，权重 2（技术术语更可能是任务关键词）
    for m in _RE_IDENT.finditer(text):
        w = m.group(0)
        low = w.lower()
        if low in _STOPWORDS or len(low) < 2:
            continue
        scores[w] += 2
    # 2) 中文：按标点/连接词切成短语块，整块作为一个候选
    for m in _RE_CJK.finditer(text):
        seg = m.group(0)
        for phrase in _split_phrases(seg):
            if len(phrase) < 2:
                continue
            if phrase in _STOPWORDS or _all_stop(phrase):
                continue
            # 短语越长越具体，权重按长度给
            scores[phrase] += len(phrase)
    # 3) 去掉被更长短语完整包含的短词（保留更具体的）
    keys = sorted(scores.keys(), key=len, reverse=True)
    kept = []
    for k in keys:
        if any(k != other and k in other for other in kept):
            continue
        kept.append(k)
    # 4) 按分数降序
    kept.sort(key=lambda w: scores[w], reverse=True)
    return kept


def _split_phrases(seg):
    """把一段连续汉字按连接词切成短语块。

    连接词/单字虚词作为边界（如「的」「和」「要」「是」「在」「，」），
    切出的每块是一个语义单元。块内不再细分。
    """
    # 切分边界：单字虚词（这些字单独出现时多为连接/助词，不宜作关键词）
    boundaries = set(
        "的 了 和 与 或 要 是 在 我 你 他 它 们 把 被 给 对 从 到 为 就 都 也 很 还 "
        "并 及 以 之 其 这 那 有 无 不 没 会 能 可 请 让 使 于 而 且 但 因 由 如 若 "
        "则 等 着 过 向 往 同 跟 按 依 据 靠 用 拿 取 做 干 搞 将 来 里 时 后 前 上 "
        "下 中 内 外 地 得 再 又 才 只 更 最 太 好 多 少 个 些 位 件 次 种 点 令"
    )
    blocks = []
    cur = []
    for ch in seg:
        if ch in boundaries:
            if cur:
                blocks.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if cur:
        blocks.append("".join(cur))
    return blocks


def _all_stop(g):
    """判断词组是否全由停用词单字组成。"""
    return all(ch in _STOPWORDS for ch in g)


def extract_from_blocks(blocks):
    """从消息 blocks 里抽出纯文本（供蒸馏用）。"""
    parts = []
    for b in (blocks or []):
        if not isinstance(b, dict):
            continue
        t = b.get("text") or b.get("code") or ""
        if t:
            parts.append(str(t))
    return "\n".join(parts)


def denoise_by_plans(keywords, threshold=0.8, recent=20):
    """跨计划去噪（方案 4.3 第 4 步）：剔除区分度太低的关键词。

    某关键词在近期计划里出现频率超过阈值，说明它几乎每轮都出现，
    对区分不同任务没有价值，予以剔除。plans 为空时不处理。
    @param keywords 候选关键词
    @param threshold 出现频率上限（超过则剔除）
    @param recent 取最近多少条计划参与统计
    @return 去噪后的关键词列表
    """
    from memory_db import get_conn
    try:
        rows = get_conn().execute(
            "SELECT text FROM plans ORDER BY created_at DESC LIMIT ?", (recent,)
        ).fetchall()
    except Exception:
        return keywords
    texts = [r["text"] or "" for r in rows]
    if not texts:
        return keywords
    n = len(texts)
    kept = []
    for k in keywords:
        freq = sum(1 for t in texts if k in t) / n
        if freq > threshold:
            continue
        kept.append(k)
    return kept


def text_to_vector(text, dim=256):
    """把文本映射为定长向量（hashing trick，零依赖）。

    中文按 2-gram、英文按标识符切分，用 CRC32 稳定映射到 dim 维桶，
    计数后做 L2 归一化，供余弦相似度检索。用 CRC32 而非内置 hash，
    保证跨进程、跨重启的桶索引一致。
    @return numpy float32 向量（dim 维）
    """
    import zlib
    import numpy as np
    vec = np.zeros(dim, dtype=np.float32)
    if not text:
        return vec
    tokens = [m.lower() for m in _RE_IDENT.findall(text)]
    for seg in _RE_CJK.findall(text):
        for i in range(len(seg) - 1):
            tokens.append(seg[i:i + 2])
    for tok in tokens:
        idx = zlib.crc32(tok.encode("utf-8")) % dim
        vec[idx] += 1.0
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec
