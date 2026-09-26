"""技能相关数据：供 System Prompt 注入的技能说明段落与技能清单。

- sections：已上线技能的统一说明，来自技能 tool.json 顶层的 prompt 字段。
- skills：已上线技能清单（仅含带说明文档、且至少有一个已上线工具的技能），
  并附带该技能包含的工具名，让 AI 在工具列表之外看到技能的完整归属。
- skills_manage：设置页管理视图，覆盖全部技能（含已下线），不参与 System Prompt 注入。
"""
import custom_tools as ct
from tool_helpers import list_skills


def sections():
    """返回已上线技能的统一说明列表：[ { skill, text } ]。"""
    return ct.prompt_sections()


def _tools_by_skill():
    """按技能名归集【已上线】工具名：{ skill_name: [工具名, ...] }。

    只统计 enabled 为真的工具：技能在 System Prompt 中的可见性由
    其是否存在已上线工具决定，与说明段落 sections() 的口径保持一致。
    """
    out = {}
    for t in ct.load_tools().values():
        if not t.get("enabled"):
            continue
        name = t.get("skill_name") or ""
        if not name:
            continue
        out.setdefault(name, []).append(t.get("name"))
    return out


def skills():
    """返回【已上线】技能清单：[ { name, summary, tools } ]，tools 为该技能包含的工具名列表。

    只纳入至少有一个已上线工具的技能：工具全部下线（含技能一键下线）后，
    该技能不再出现在 System Prompt 的技能列表中，避免与 sections() 口径不一致。
    设置页所需的「全部技能」视图由 skills_manage() 单独提供，不受此处过滤影响。
    """
    by_skill = _tools_by_skill()
    out = []
    for s in list_skills():
        tools = sorted(by_skill.get(s["name"], []))
        if not tools:
            continue
        out.append({
            "name": s["name"],
            "summary": s["summary"],
            "tools": tools,
        })
    return out


def _skill_dirs():
    """本机 skills 根目录下所有技能目录名集合（含尚无工具、无说明文档的）。"""
    from tool_helpers import SKILLS_ROOT
    out = []
    if not SKILLS_ROOT.is_dir():
        return out
    for d in sorted(SKILLS_ROOT.iterdir(), key=lambda x: x.name):
        if d.is_dir() and not d.name.startswith("."):
            out.append(d.name)
    return out


def skills_manage():
    """技能管理视图，供设置页「技能」区块渲染。

    与 skills() 的区别：
    - 覆盖 skills 根目录下的全部技能，而非只含带说明文档的；
    - 每个技能附带其包含的完整工具定义（含 enabled 与来源信息），
      便于界面直接渲染工具行与一键上下线开关；
    - 附带文档路径约定，供界面编辑 SKILL.md。
    """
    # 按技能归集工具定义：{ skill_name: [工具完整信息, ...] }
    by_skill = {}
    for t in ct.load_tools().values():
        name = t.get("skill_name") or ""
        if not name:
            continue
        by_skill.setdefault(name, []).append({
            "name": t.get("name"),
            "description": t.get("description", ""),
            "enabled": bool(t.get("enabled")),
            "provider": t.get("provider", ""),
            "executor": t.get("executor", "script"),
            "parameters": t.get("parameters") or [],
        })
    # 技能摘要：优先取 SKILL.md / README.md 首行
    summaries = {s["name"]: s["summary"] for s in list_skills()}
    names = set(_skill_dirs()) | set(by_skill.keys())
    out = []
    for name in sorted(names):
        tools = sorted(by_skill.get(name, []), key=lambda x: x.get("name") or "")
        enabled_count = sum(1 for x in tools if x.get("enabled"))
        out.append({
            "name": name,
            "summary": summaries.get(name, ""),
            "tools": tools,
            "tool_count": len(tools),
            "enabled_count": enabled_count,
            "doc_file": "SKILL.md",
        })
    return out
