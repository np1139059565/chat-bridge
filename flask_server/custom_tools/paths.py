"""自定义工具（来自标准 skill）—— 路径与常量

集中定义自定义工具子系统使用的目录基准与命名约束：
- APP_DIR / PROJECT_ROOT     服务目录与工程根目录
- DEFAULT_SKILL_ROOTS        默认可扫描的 skill 根目录列表
- NAME_RE                    工具名 / 参数名的合法字符约束
- 路径互转辅助：项目根相对路径 ↔ 绝对路径

拆出本模块的原因：路径解析被 loader / registry / scan 共用，集中一处可避免
各处重复推导路径基准，也便于工程迁移时只改一个地方。

工具的持久化读写走 definition.yaml / runtime.yaml 的 custom_tools 分区
（见 core/config_file.py），本模块不再持有落盘文件路径。
"""
import re
from pathlib import Path

import paths

# 服务目录与工程根统一由 paths 提供
APP_DIR = paths.APP_DIR
PROJECT_ROOT = paths.PROJECT_ROOT

# 工具名 / 参数名：仅允许字母、数字、下划线
NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def to_project_rel(abs_path: Path) -> str:
    """将绝对路径转为相对项目根的字符串；不在项目根内则保留绝对路径。"""
    p = abs_path.resolve()
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


def resolve_to_abs(stored: str) -> Path:
    """将存储的路径解析为绝对路径。绝对路径直接使用；相对路径视为相对于项目根。"""
    p = Path(stored)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p.resolve()


def default_roots():
    """可扫描的默认 skill 根目录（用户同意「完全信任」，这里只是提供方便的默认入口）。"""
    roots = [
        PROJECT_ROOT / "skills",                    # 项目自带 skill 模板（基础路径）
        Path.home() / ".codebuddy" / "skills",       # 用户级 skill
        Path.home() / ".codebuddy" / "skills-marketplace" / "skills",
    ]
    out = []
    for p in roots:
        try:
            if p.is_dir():
                out.append(p)
        except Exception:
            pass
    return out


# 启动时计算一次默认根目录列表
DEFAULT_SKILL_ROOTS = default_roots()
