"""自定义工具（来自标准 skill）—— 目录扫描

扫描某个目录下的可安装 skill（含 tool.json 的子目录），只返回尚未安装的工具清单，
供设置页「扫描可安装」使用。已安装的工具不再出现在扫描结果里；有 tool.json 且
工具全部已安装的 skill 整条略过。无 tool.json 的说明文档型 skill 仍登记为空技能，
它没有可安装条目，不属于「已安装条目」。

单个 skill 解析失败不影响其它 skill：错误信息随该条目一并返回。
"""
from pathlib import Path

from .loader import parse_skill
from .paths import PROJECT_ROOT, to_project_rel
from .registry import load_tools


def _resolve_scan_root(d):
    """把扫描入参解析为绝对目录并校验存在性。"""
    root = Path(d)
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    if not root.is_dir():
        raise ValueError("目录不存在：" + str(root))
    return root


def _scan_one_skill(sub, installed):
    """扫描单个 skill 子目录，返回结果条目；解析失败时携带 error 字段。

    扫描结果只呈现还可安装的条目：已安装的工具直接过滤；有 tool.json 且工具
    全部已安装的 skill 返回 None，由 scan_dir 整条略过。无 tool.json（只有说明
    文档）的技能视为合法技能：工具列表为空、没有已安装条目，照常登记为空技能。
    """
    if not (sub / "tool.json").exists():
        # 无工具定义：仅作为「空技能」登记，供设置页上下线
        return {
            "skill_dir": to_project_rel(sub),
            "skill_name": sub.name,
            "tools": [],
        }
    try:
        parsed = parse_skill(sub)
        # 只保留未安装工具；保留 installed 字段维持响应形状，取值恒为 False
        tools = [{
            "name": t["name"],
            "description": t["description"],
            "installed": False,
        } for t in parsed if t["name"] not in installed]
        # 工具全部已安装：整条不返回，避免扫描块里只剩一个空技能名
        if not tools:
            return None
        return {
            "skill_dir": to_project_rel(sub),
            "skill_name": sub.name,
            "tools": tools,
        }
    except Exception as e:
        # 单个 skill 解析失败：记录错误，继续扫描其它 skill
        return {
            "skill_dir": to_project_rel(sub),
            "skill_name": sub.name,
            "error": str(e),
            "tools": [],
        }


def _looks_like_skill(sub):
    """判断子目录是否像一个 skill：含 tool.json，或含说明文档（SKILL.md / README.md）。"""
    if (sub / "tool.json").exists():
        return True
    return (sub / "SKILL.md").exists() or (sub / "README.md").exists()


def scan_dir(d):
    """扫描某目录下的可安装 skill，只返回尚未安装的工具条目。"""
    root = _resolve_scan_root(d)
    installed = load_tools()
    results = []
    for sub in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda x: x.name):
        # 处理含 tool.json 或说明文档的子目录；其余视为普通目录跳过
        if not _looks_like_skill(sub):
            continue
        entry = _scan_one_skill(sub, installed)
        # 工具全部已安装的 skill 不进入扫描结果
        if entry is not None:
            results.append(entry)
    return results
