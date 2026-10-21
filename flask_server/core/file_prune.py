"""临时文件目录回收（统一实现）

职责：按数量上限清理各临时目录，并保护仍被引用的文件。

为何集中：
    截图、网页图片、QQ 图片、语音、分段读取落盘各自成目录，
    此前只有网页音频有回收，其余四个目录无上限、只增不减。
    清理规则是同一套（数量上限 + 引用保护），集中一处便于统一口径。

保护原则：
    这些文件都是「可重新生成」的产物，但消息可能引用它们。
    仍被引用的文件一律保留，否则会出现「消息还在、图片/音频打不开」。
"""
import app_log


def log(*args):
    """统一前缀日志，便于按来源检索。"""
    app_log.warn("[prune]", *args)


def prune_dir(dir_path, max_keep, keep_names=None):
    """按数量上限清理一个目录，保护 keep_names 中的文件。

    规则：
      1. 引用保护——名字在 keep_names 中的文件一律不删；
      2. 数量上限——其余文件只保留最近 max_keep 个（按修改时间）。
    删除失败静默跳过，下次再补删——清理是尽力而为，不影响主流程。

    @param dir_path   目录（pathlib.Path）
    @param max_keep   保留的文件数上限
    @param keep_names 需保护的文名集合；None 视为无保护
    @returns 实际删除的文件数
    """
    try:
        # 目录不存在：无需清理
        if not dir_path.is_dir():
            return 0
        # 只处理普通文件，忽略可能的子目录
        files = [f for f in dir_path.iterdir() if f.is_file()]
        # 未超上限：直接返回，避免无谓的 stat 开销
        if len(files) <= max_keep:
            return 0
        keep = keep_names or set()
        # 超出上限、需要删掉的个数
        need = len(files) - max_keep
        # 可删候选：未被引用的文件，按修改时间升序（最旧在前）
        removable = [f for f in files if f.name not in keep]
        removable.sort(key=lambda f: f.stat().st_mtime)
        removed = 0
        # 从最旧的可删文件开始删，最多删 need 个；被引用的一个都不动
        for f in removable[:need]:
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
        if removed:
            log("清理 %s：删除 %d 个（上限 %d）" % (dir_path.name, removed, max_keep))
        return removed
    except Exception as e:
        log("清理目录失败：%s" % e)
        return 0
