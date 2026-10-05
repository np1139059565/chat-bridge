"""AI 工具调用镜像插件 —— 记忆系统：笔记层

职责：承载两类文本记忆，全部存进数据库（不再写 Markdown 文件）：
  1. journal  —— 每日记忆条目（按日期 day 组织）；
  2. notebook —— 错题本条目（永久累积）。

这两类原本以 Markdown 文件形式存在 memory/ 目录下，现迁移入库，
经接口读写；数据库为唯一权威。

依赖：memory_db、time、json
"""
import json
import time

from memory_db import get_conn, maybe_commit


def _now():
    """当前 Unix 时间戳（秒）。"""
    return int(time.time())


def _day_str(day=None):
    """取日期字符串 YYYY-MM-DD；day 为空则取今天。"""
    return day or time.strftime("%Y-%m-%d")


def add_note(kind, text, day=None, node_id=0, keywords=None):
    """写入一条笔记。

    @param kind 'journal' 或 'notebook'
    @param text 正文
    @param day  仅 journal 用（YYYY-MM-DD），缺省取今天
    @param node_id 关联的记忆节点 id（0 表示无）
    @param keywords 关键词列表
    @return 新条目 id
    """
    conn = get_conn()
    day_val = _day_str(day) if kind == "journal" else None
    kw_json = json.dumps(keywords or [], ensure_ascii=False)
    cur = conn.execute(
        "INSERT INTO notes (kind, day, node_id, text, keywords, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (kind, day_val, int(node_id or 0), text, kw_json, _now()),
    )
    maybe_commit(conn)
    return cur.lastrowid


def list_notes(kind=None, day=None, limit=200):
    """按类型 / 日期列举笔记，按时间升序。

    @param kind 'journal' / 'notebook'；None 表示全部
    @param day  仅对 journal 生效；None 表示不限日期
    @return 条目 dict 列表
    """
    conn = get_conn()
    sql = "SELECT * FROM notes WHERE 1=1"
    args = []
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if day:
        sql += " AND day=?"
        args.append(day)
    sql += " ORDER BY created_at, id LIMIT ?"
    args.append(int(limit))
    rows = conn.execute(sql, args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["keywords"] = _loads(d.get("keywords"), [])
        out.append(d)
    return out


def list_days(kind="journal", limit=60):
    """列出有笔记的日期（倒序），供前端按天浏览每日记忆。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT day FROM notes WHERE kind=? AND day IS NOT NULL"
        " ORDER BY day DESC LIMIT ?", (kind, int(limit))
    ).fetchall()
    return [r["day"] for r in rows]


def delete_note(note_id):
    """删除一条笔记，返回是否删除成功。"""
    conn = get_conn()
    cur = conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
    maybe_commit(conn)
    return cur.rowcount > 0


def _loads(text, default):
    """安全反序列化 JSON。"""
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default
