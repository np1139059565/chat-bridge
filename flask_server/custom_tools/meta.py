"""自定义工具（来自标准 skill）—— 对外视图

职责：把注册表中的工具投影为不同用途的视图：
- external_providers：已上线的 executor=external 工具，按 provider 分组
- prompt_sections：各技能的统一说明段落（供 System Prompt 注入）
- public_meta / all_meta：已上线工具的精简视图（供 /tools）
- all_meta_full：全部工具（含未上线）的完整视图（供设置页管理 UI）
"""
from .registry import load_tools


def external_providers():
    """汇总【已上线】的 executor=external 工具，按 provider 分组，用于注册到提供方注册表。

    未上线的外部工具不注册，因此即使提供方在线也不会并入 /tools。
    """
    groups = {}
    for t in load_tools().values():
        if (t.get("executor") or "script") != "external":
            continue
        if not t.get("enabled"):
            continue
        provider = (t.get("provider") or "").strip()
        if not provider:
            continue
        entry = {
            "name": t.get("name"),
            "description": t.get("description", ""),
            "parameters": t.get("parameters") or [],
        }
        if t.get("silent"):
            entry["silent"] = True
        groups.setdefault(provider, []).append(entry)
    return groups


def prompt_sections():
    """收集各技能的统一说明（tool.json 的 prompt 字段）。

    生效条件：该技能下有至少一个工具处于上线状态。
    返回 [ { skill, text } ]，技能名取 skill_name。
    """
    sections = {}
    for t in load_tools().values():
        if not t.get("enabled"):
            continue
        text = (t.get("skill_prompt") or "").strip()
        if not text:
            continue
        skill = t.get("skill_name") or ""
        sections[skill] = text
    return [{"skill": k, "text": v} for k, v in sections.items()]


def public_meta(tool):
    """单个工具的精简视图（名称 + 描述 + 参数 + silent 标记）。"""
    meta = {
        "name": tool.get("name"),
        "description": tool.get("description", ""),
        "parameters": tool.get("parameters") or [],
    }
    # silent：一次性副作用工具，其结果不回传网页 AI
    if tool.get("silent"):
        meta["silent"] = True
    return meta


def all_meta():
    """已上线的自定义工具（用于 /tools 合并进 System Prompt）。

    上线即在此返回，与执行端是否在线无关：executor=external 的工具若提供方离线，
    调用时返回离线错误，但不从工具列表撤出。
    """
    return [public_meta(t) for t in load_tools().values() if t.get("enabled")]


def all_meta_full():
    """全部自定义工具（含未上线），用于设置页管理 UI。"""
    return [{
        "name": t.get("name"),
        "description": t.get("description", ""),
        "skill_name": t.get("skill_name", ""),
        "skill_dir": t.get("skill_dir", ""),
        "script": t.get("script", ""),
        "interpreter": t.get("interpreter", ""),
        "arg_style": t.get("arg_style", ""),
        "enabled": bool(t.get("enabled")),
        "parameters": t.get("parameters") or [],
        "fixed_args": t.get("fixed_args") or [],
    } for t in load_tools().values()]
