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
        # 只统计真正的 AI 工具：指令执行端（kind=command_action）不进 System Prompt
        if (t.get("kind") or "tool") != "tool":
            continue
        name = t.get("skill_name") or ""
        if not name:
            continue
        out.setdefault(name, []).append(t.get("name"))
    return out


def skills():
    """返回【已上线】技能清单：[ { name, summary, tools } ]，tools 为该技能包含的工具名列表。

    是否上线由技能自身的开关决定，与「有没有工具」无关：没有工具、只有说明文档
    的技能同样纳入（tools 为空列表），其说明经 sections() 注入 System Prompt，
    口径与 sections() 保持一致。技能集合以技能目录为准，摘要缺失时为空串。
    设置页所需的「全部技能」视图由 skills_manage() 单独提供。
    """
    from custom_tools.skills import is_skill_online, skill_dir_map
    by_skill = _tools_by_skill()
    summaries = {s["name"]: s["summary"] for s in list_skills()}
    out = []
    for name in sorted(skill_dir_map().keys()):
        if not is_skill_online(name):
            continue
        out.append({
            "name": name,
            "summary": summaries.get(name, ""),
            "tools": sorted(by_skill.get(name, [])),
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


def _manage_tools_by_skill():
    """按技能归集【全部】工具定义（含已下线）：{ skill_name: [工具完整信息, ...] }。

    与 _tools_by_skill() 的区别：此处不过滤 enabled，因为设置页需要
    展示并操作下线中的工具。
    """
    by_skill = {}
    for t in ct.load_tools().values():
        # 只归集真正的 AI 工具：指令执行端（kind=command_action）不进设置页技能区
        if (t.get("kind") or "tool") != "tool":
            continue
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
    return by_skill


def _manage_row(name, tools, summaries, enabled):
    """组装设置页单个技能的行：摘要、工具列表、上下线计数与技能自身开关。

    enabled 为技能自身的上线状态（与工具是否上线解耦），供界面渲染一键开关；
    tool_count 可能为 0（无工具技能），此时开关仍可用。
    """
    tools = sorted(tools, key=lambda x: x.get("name") or "")
    return {
        "name": name,
        "summary": summaries.get(name, ""),
        "tools": tools,
        "enabled": bool(enabled),
        "tool_count": len(tools),
        "enabled_count": sum(1 for x in tools if x.get("enabled")),
        "doc_file": "SKILL.md",
    }


def skills_manage():
    """技能管理视图，供设置页「技能」区块渲染。

    与 skills() 的区别：
    - 覆盖全部技能（技能目录 ∪ 已安装工具所属技能），而非只含已上线的；
    - 每个技能附带其包含的完整工具定义（含 enabled 与来源信息），
      便于界面直接渲染工具行与一键上下线开关；
    - 附带技能自身开关状态，无工具技能同样可被上下线；
    - 附带文档路径约定，供界面编辑 SKILL.md。
    """
    from custom_tools.skills import is_skill_online, skill_dir_map
    by_skill = _manage_tools_by_skill()
    # 技能摘要：优先取 SKILL.md / README.md 首行
    summaries = {s["name"]: s["summary"] for s in list_skills()}
    names = sorted(set(skill_dir_map().keys()) | set(by_skill.keys()))
    return [_manage_row(n, by_skill.get(n, []), summaries, is_skill_online(n)) for n in names]
