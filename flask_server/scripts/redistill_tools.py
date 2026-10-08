"""记忆维护脚本：用当前蒸馏逻辑重蒸历史「工具节点」。

背景：工具节点的蒸馏逻辑修复后，历史节点的精华/关键词仍是旧逻辑产物
（如腰斩的 JSON 片段）。本脚本遍历库中 source='tool' 的节点，用现行
_essence_for / 关键词提取重算蒸馏层字段并写回。原始 blocks 不动，
故可随时重跑、不损失原始内容。

用法（在 flask_server 目录下）：
    python scripts/redistill_tools.py            # 实际写库
    python scripts/redistill_tools.py --dry-run  # 只预演，不写库

依赖：core/ 与 flask_server/ 需在模块搜索路径中（脚本内已注入）。
"""
import os
import sys

# 把 core 与 flask_server 加入模块搜索路径，保证扁平导入可用。
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # flask_server/
for _p in (os.path.join(_ROOT, "core"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import memory_nodes
import memory_distill as md
import memory_keywords as kw
from memory_db import get_conn


def redistill(dry_run=False):
    """重蒸全部工具节点。

    @param dry_run True 时只统计会变化的节点数，不写库
    @return (处理数, 精华有变化数)
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT id FROM nodes WHERE source='tool' AND deleted=0"
    ).fetchall()
    total = len(rows)
    changed = 0
    done = 0
    for r in rows:
        nid = r["id"]
        node = memory_nodes.get_node(nid)
        if not node:
            continue
        text = kw.extract_from_blocks(node.get("blocks"))
        ess = md._essence_for("tool", text, node.get("blocks"))
        if ess != (node.get("essence") or ""):
            changed += 1
        if dry_run:
            continue
        # 与 distill_node 口径一致：工具节点从精华提词，更干净。
        kw_source = ess if ess else text
        kws = kw.denoise_by_plans(kw.extract(kw_source, top_k=8))
        vec = kw.text_to_vector(ess or text)
        memory_nodes.set_essence(nid, ess, kws, vec)
        done += 1
    return total, changed, done


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    total, changed, done = redistill(dry_run=dry)
    mode = "预演" if dry else "已写回"
    print("工具节点总数=%d，精华会变化/已变化=%d，%s=%d" % (total, changed, mode, done))
