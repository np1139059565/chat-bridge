"""AI 工具调用镜像插件 —— 记忆系统：消息块文本抽取（共享）

职责：把记忆节点的 blocks 列表拍平成一段纯文本，供蒸馏与抽检对比使用。

背景：蒸馏（memory_keywords）与抽检（memory_quality_impl）都需要把
blocks 里的 text / code 字段拼成纯文本，此前各自实现了一份，
本模块集中此逻辑，供两处共用，避免重复维护。

依赖：无（纯函数，零外部依赖）
"""


def blocks_to_text(blocks, strip=False):
    """把消息 blocks 抽成一段纯文本。

    逐个块取出 text 或 code 字段，非空则收集，最后用换行拼接。
    @param blocks 消息块列表（可能为 None 或含非字典项）
    @param strip  是否对结果去首尾空白；默认 False（保持原样）
    @returns 拼接后的纯文本；无有效内容则返回空串
    """
    parts = []                                  # 收集各块文本
    for b in (blocks or []):                    # 遍历块列表，None 视为空
        if not isinstance(b, dict):             # 跳过非字典项（脏数据防御）
            continue
        t = b.get("text") or b.get("code") or ""  # 取文本块或代码块内容
        if t:                                   # 非空才收集
            parts.append(str(t))                # 统一转字符串
    text = "\n".join(parts)                     # 换行拼接
    return text.strip() if strip else text      # 按需去首尾空白
