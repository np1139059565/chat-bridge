"""网页音频目录回收

职责：按数量上限清理网页音频目录，并保护仍被收件箱消息引用的文件。

为何独立成模块：
- 清理策略是「保留多少、删哪些」的独立规则，与镜像主流程无关；
- 引用保护依赖收件箱结构，单独成文便于随时替换判据而不动主流程。

保护原则：音频是可重新合成的产物，但消息会引用它。仍被引用的文件
一律保留，否则会出现「消息还在、语音打不开」。
"""
import app_log
from app_limits import MAX_AUDIO_FILES

from . import web_inbox


def log(*args):
    """统一前缀日志：与镜像模块同一前缀，便于按来源检索。"""
    app_log.warn("[web][mirror]", *args)


def referenced_audio():
    """取收件箱中仍被消息引用的音频文件名集合（引用保护）。

    被引用的音频即使很旧也不能删，否则用户翻到那条消息时语音会 404。
    @returns 文件名集合；取不到时返回空集（退化为仅按上限清理）
    """
    try:
        state = web_inbox._read_state()
        out = set()
        for m in (state.get("messages") or []):
            v = m.get("voice")
            if v:
                out.add(str(v))
        return out
    except Exception:
        return set()


def prune_audio_files(max_keep=MAX_AUDIO_FILES):
    """回收网页音频目录：保留最近 max_keep 个文件，且绝不删被消息引用的。

    双重保护：
      1. 引用保护——仍被收件箱消息引用的音频一律保留；
      2. 数量上限——其余文件只保留最近 max_keep 个。
    按修改时间排序保留最新的（同毫秒生成的文件按文件名排序可能错乱，mtime 才稳）。
    删除失败静默跳过，下次再补删——清理是「尽力而为」，不影响主流程。
    @param max_keep 保留的文件数上限
    @returns 实际删除的文件数
    """
    try:
        import paths
        d = paths.WEB_AUDIO_DIR
        # 目录不存在：无需清理
        if not d.is_dir():
            return 0
        # 只处理普通文件，忽略可能的子目录
        files = [f for f in d.iterdir() if f.is_file()]
        # 未超上限：直接返回，避免无谓的 stat 开销
        if len(files) <= max_keep:
            return 0
        keep_ref = referenced_audio()
        # 超出上限、需要删掉的个数
        need = len(files) - max_keep
        # 可删候选：未被消息引用的文件，按修改时间升序（最旧在前）
        removable = [f for f in files if f.name not in keep_ref]
        removable.sort(key=lambda f: f.stat().st_mtime)
        removed = 0
        # 从最旧的可删文件开始删，最多删 need 个；被引用的一个都不动。
        for f in removable[:need]:
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
        return removed
    except Exception as e:
        log("清理音频目录失败：", e)
        return 0
