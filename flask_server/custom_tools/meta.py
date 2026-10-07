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
        # wakeup：唤醒类工具随命令透传给 hub，供 poll 在抽屉关闭时放行
        if t.get("wakeup"):
            entry["wakeup"] = True
        # kind=command_action：指令的执行端。仍需注册进 hub（执行通道与工具共用，
        # 指令 dispatch 要靠 find_tool 找到它读 wakeup 等）；但不进 AI 工具目录，
        # 由 provider_tools() 按 kind 过滤。
        if (t.get("kind") or "tool") == "command_action":
            entry["kind"] = "command_action"
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
    # silent：仅在界面不生成工具卡片；结果照常回传
    if tool.get("silent"):
        meta["silent"] = True
    return meta


def all_meta():
    """已上线的自定义工具（用于 /tools 合并进 System Prompt）。

    上线即在此返回，与执行端是否在线无关：executor=external 的工具若提供方离线，
    调用时返回离线错误，但不从工具列表撤出。
    只含 kind=tool 的条目：指令执行端（kind=command_action）对 AI 透明，
    不进 AI 工具目录。源头已在声明层分开，此处按来源身份天然分流。
    """
    return [public_meta(t) for t in load_tools().values()
            if t.get("enabled") and (t.get("kind") or "tool") == "tool"]


def all_meta_full():
    """全部自定义【AI 工具】（含未上线），用于设置页管理 UI。

    只含 kind=tool 的条目：指令执行端（kind=command_action）是指令的内部实现，
    不属于用户可管理的 AI 工具，一律不进此视图 —— 设置页因此不再出现指令。
    """
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
    } for t in load_tools().values() if (t.get("kind") or "tool") == "tool"]
