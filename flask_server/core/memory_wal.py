"""AI 工具调用镜像插件 —— 记忆库 WAL 维护

职责：主动执行 SQLite 的 WAL checkpoint，把 -wal 内容合并回主库并截断回收。
从 memory_db.py 拆出，使该文件保持在行数上限内，并让「WAL 维护」这一
独立关注点自成一体。

为什么需要主动调用：
    SQLite 的自动 checkpoint 默认是 PASSIVE 模式——只要有其它连接
    （本项目后台常驻线程的连接长期不关）还开着 WAL 文件，它就不截断，
    WAL 只增不减（曾观察到 42MB 未回收）。主动 checkpoint 才能把
    -wal 文件缩回去。

依赖：memory_db（复用其连接管理）
"""
import sqlite3

from memory_db import get_conn


# 合法的 checkpoint 模式白名单：
#   TRUNCATE —— 合并后把 -wal 截断为 0，回收磁盘空间；
#   PASSIVE  —— 不阻塞其它连接，但不保证截断；
#   FULL     —— 等待所有读事务结束后合并；
#   RESTART  —— 同 FULL，并把 WAL 重置到开头。
_VALID_MODES = ("TRUNCATE", "PASSIVE", "FULL", "RESTART")


def wal_checkpoint(mode="TRUNCATE"):
    """主动执行 WAL checkpoint：把 -wal 内容合并回主库并截断回收。

    并发安全：TRUNCATE 需要短暂独占，可能阻塞写事务；本函数靠连接的
    busy_timeout 自旋等待，拿不到就放弃本轮（下次再试），绝不强占。

    @param mode checkpoint 模式（TRUNCATE / PASSIVE / FULL / RESTART）
    @return dict { ok, mode, busy, log_pages, checkpointed } 或含 error 的失败字典
    """
    # 白名单校验：PRAGMA 不支持参数占位，靠白名单防拼串注入
    if mode not in _VALID_MODES:
        mode = "TRUNCATE"
    conn = get_conn()
    try:
        # wal_checkpoint 返回一行三列：(busy, log_pages, checkpointed_pages)
        row = conn.execute("PRAGMA wal_checkpoint(%s)" % mode).fetchone()
    except sqlite3.OperationalError as e:
        # 拿不到锁或库暂不可用：不抛，交由调用方按失败处理、下轮重试
        return {"ok": False, "mode": mode, "error": str(e)}
    busy = row[0] if row else None
    log_pages = row[1] if row else None
    ckpt_pages = row[2] if row else None
    return {"ok": busy == 0, "mode": mode, "busy": busy,
            "log_pages": log_pages, "checkpointed": ckpt_pages}
