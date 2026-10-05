"""AI 工具调用镜像插件 —— 记忆系统：固化层

职责（方案第七节·固化层）：把反复验证的记忆节点固化为长期资产：
  1. promote_to_rule  —— 把经验升级为规则文件（rules/*.md）；
  2. promote_to_notebook —— 写入错题本（数据库 notes 表）。

固化是「记忆 → 规则」的升格通道：节点来自记忆库，规则产物落到规则文件，
错题本产物落到数据库。规则文件是人可读、可编辑、可版本控制的 Markdown。

依赖：paths、memory_nodes、memory_notes、time
"""
import time

import paths
import memory_nodes
import memory_notes


def _stamp():
    """生成人类可读时间戳（固化记录用）。"""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime())


def promote_to_rule(node_id, rule_name, title=""):
    """把某节点固化为一条规则文件。

    取节点的精华与关键词，写成 rules/<rule_name>.md。若文件已存在，
    追加一条带时间戳的条目而非覆盖，保留历史沉淀。
    @param node_id 记忆节点 id
    @param rule_name 规则名（文件名，不含扩展名）
    @param title 可选标题；缺省用规则名
    @return dict { rule, appended } 或 None（节点不存在）
    """
    node = memory_nodes.get_node(node_id)
    if not node:
        return None
    essence = (node.get("essence") or "").strip()
    keywords = node.get("keywords") or []
    rule_path = paths.RULES_DIR / (str(rule_name) + ".md")
    paths.RULES_DIR.mkdir(parents=True, exist_ok=True)
    entry = "- [%s] %s" % (_stamp(), essence)
    if keywords:
        entry += "（关键词：%s）" % "、".join(keywords)
    appended = rule_path.exists()
    if appended:
        with open(rule_path, "a", encoding="utf-8") as f:
            f.write("\n" + entry + "\n")
    else:
        head = ("# %s\n\n" % (title or rule_name))
        with open(rule_path, "w", encoding="utf-8") as f:
            f.write(head + entry + "\n")
    return {"rule": rule_name, "appended": appended}


def promote_to_notebook(node_id, note=""):
    """把某节点写入错题本（数据库 notes 表，kind=notebook）。

    错题本是永久记忆，跨天累积。追加一条带时间戳与来源的条目，不覆盖既有内容。
    @param node_id 记忆节点 id
    @param note 可选补充说明
    @return dict { notebook, note_id } 或 None（节点不存在）
    """
    node = memory_nodes.get_node(node_id)
    if not node:
        return None
    essence = (node.get("essence") or "").strip()
    keywords = node.get("keywords") or []
    text = "[%s] %s" % (_stamp(), essence)
    if note:
        text += "\n备注：%s" % note
    nid = memory_notes.add_note("notebook", text, node_id=node_id, keywords=keywords)
    return {"notebook": "error-notebook", "note_id": nid}
