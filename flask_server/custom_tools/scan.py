"""自定义工具（来自标准 skill）—— 目录扫描

扫描某个目录下的可安装 skill（含 tool.json 的子目录），返回每个 skill 的工具清单
与安装状态，供设置页「扫描可安装」使用。

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
    """扫描单个 skill 子目录，返回结果条目；解析失败时携带 error 字段。"""
    try:
        parsed = parse_skill(sub)
        return {
            "skill_dir": to_project_rel(sub),
            "skill_name": sub.name,
            "tools": [{
                "name": t["name"],
                "description": t["description"],
                "installed": t["name"] in installed,
            } for t in parsed],
        }
    except Exception as e:
        # 单个 skill 解析失败：记录错误，继续扫描其它 skill
        return {
            "skill_dir": to_project_rel(sub),
            "skill_name": sub.name,
            "error": str(e),
            "tools": [],
        }


def scan_dir(d):
    """扫描某目录下的可安装 skill（含 tool.json 的子目录）。"""
    root = _resolve_scan_root(d)
    installed = load_tools()
    results = []
    for sub in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda x: x.name):
        # 仅处理含 tool.json 的子目录（其余视为普通目录跳过）
        if not (sub / "tool.json").exists():
            continue
        results.append(_scan_one_skill(sub, installed))
    return results
