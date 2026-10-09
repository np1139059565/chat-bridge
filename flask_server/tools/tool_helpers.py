"""AI 工具调用镜像插件 —— 工具通用辅助

本模块被 tools_impl.py 引用，提供所有工具共用的参数校验、路径解析与结果体积控制：

- ToolParamError   参数错误异常（与「工具内部代码缺陷」区分）
- PROJECT_ROOT / SKILLS_ROOT  路径基准
- abspath                    路径解析（相对路径以工程根为基准）
- resolve_skill_file          skill 内相对路径解析与越界校验
- normalize_aliases / require 参数别名归一与必填校验
- max_json_chars / dump_len / enforce_size_limit  结果 JSON 体积上限控制

拆出本模块的目的：把不随调用变化的通用辅助与工具实现分离，
使 tools_impl.py 只聚焦 t_xxx 实现与派发表。
"""
import json
from pathlib import Path

import paths
import yaml_utils


class ToolParamError(Exception):
    """参数错误：调用方传入的参数不合法，调整参数即可重试。

    与「工具内部代码缺陷」区分开，便于 AI 判断该改参数还是该修代码。
    """


# 工程根目录与 skills 根目录：统一由 paths 提供，避免各处用 __file__ 重复推导。
PROJECT_ROOT = paths.PROJECT_ROOT
SKILLS_ROOT = paths.SKILLS_ROOT


def abspath(p):
    """把入参解析为绝对路径（通用工具用）：绝对路径原样，相对路径以工程根为基准。"""
    p = Path(p)
    if p.is_absolute():
        return p.resolve()
    return (PROJECT_ROOT / p).resolve()


def _require_single_dir_name(skill):
    """校验 skill 名：非空、单层目录名（防止用 ../ 越出 skills 目录）。"""
    skill = str(skill or "").strip()
    if not skill or "/" in skill or "\\" in skill or skill in (".", ".."):
        raise ToolParamError("skill 名非法：%s（应为 skills/ 下的单层目录名，如 debug_chrome）" % skill)
    return skill


def _list_available_skills():
    """列出 skills 根目录下可用的 skill 名，用于错误提示。"""
    if not SKILLS_ROOT.is_dir():
        return []
    return sorted([d.name for d in SKILLS_ROOT.iterdir() if d.is_dir()])


def _first_content_line(text):
    """取正文首个说明句：跳过 YAML front matter 与 Markdown 标题行，截断 120 字。

    优先返回非标题的正文首行（标题通常是技能名本身，信息量低）；
    若全文只有标题，则回退为标题文本。
    """
    lines = text.splitlines()
    i = 0
    # 跳过以 --- 包裹的 YAML front matter，避免把元数据当成正文摘要
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        i += 1
    fallback = ""
    for line in lines[i:]:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            # 标题行：仅作为兜底候选，继续找正文
            if not fallback:
                fallback = s.lstrip("#").strip()
            continue
        return s[:120]
    return fallback[:120]


def skill_summary(skill_dir):
    """取技能摘要：优先 SKILL.md，其次 README.md，取正文首个非空行。"""
    for name in ("SKILL.md", "README.md"):
        f = skill_dir / name
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        summary = _first_content_line(text)
        if summary:
            return summary
    return ""


def list_skills():
    """列出本机可用技能：[{name, summary}]，仅含带说明文档（SKILL.md / README.md）的目录。"""
    if not SKILLS_ROOT.is_dir():
        return []
    out = []
    for d in sorted(SKILLS_ROOT.iterdir(), key=lambda x: x.name):
        if not d.is_dir() or d.name.startswith("."):
            continue
        summary = skill_summary(d)
        if not summary:
            continue
        out.append({"name": d.name, "summary": summary})
    return out


def resolve_skill_file(skill, rel):
    """把 (skill 名, skill 内相对路径) 解析为绝对路径，并做越界校验。

    - skill 名仅允许单层目录名，防止用 ../ 越出 skills 目录。
    - rel 必须是 skill 目录内的相对路径，解析后仍须落在该 skill 目录内。
    """
    skill = _require_single_dir_name(skill)
    rel = str(rel or "").strip()
    if not rel:
        raise ToolParamError("缺少必填参数 file（skill 目录内的相对路径，如 SKILL.md）")
    base = (SKILLS_ROOT / skill).resolve()
    if not base.is_dir():
        available = _list_available_skills()
        raise ToolParamError("skill 不存在：%s（可用：%s）" % (skill, ", ".join(available) or "无"))
    target = (base / rel).resolve()
    # 越界校验：解析后的目标路径必须仍在 skill 目录内
    if base != target and base not in target.parents:
        raise ToolParamError("file 越出 skill 目录：%s" % rel)
    return target


# 参数别名：调用方可能用 path / file 等写法指代 filePath，统一归一到规范名，
# 避免因别名导致「缺参」报错。
# 参数别名：调用方可能用 camelCase / 旧名指代规范参数，统一归一到规范名，
# 避免因别名导致「缺参」报错。规范名口径：文件路径=file_path，目录路径=dir_path。
_PARAM_ALIASES = {
    # 文件路径 → file_path
    "path": "file_path",
    "file": "file_path",
    "filePath": "file_path",
    "filepath": "file_path",
    "target_file": "file_path",
    # 目录路径 → dir_path
    "target_directory": "dir_path",
    "dirPath": "dir_path",
    "directory": "dir_path",
    # 替换文本 → old_string / new_string
    "old_str": "old_string",
    "new_str": "new_string",
    # 其它 camelCase → snake_case
    "contextAround": "context_around",
    "caseSensitive": "case_sensitive",
}


def normalize_aliases(p):
    """把别名参数归一到规范参数名（仅补缺失项，不覆盖已有值）。"""
    if not isinstance(p, dict):
        return p
    for alias, real in _PARAM_ALIASES.items():
        if alias in p and real not in p:
            p[real] = p.get(alias)
    return p


def require(p, *names):
    """校验必填参数；缺失 / 空串时抛 ToolParamError，并明确告知正确参数名。

    目的是避免 AI 臆造别名（如把 file_path 写成 path）后工具静默用默认值、
    返回成功却结果错误，使调用方无从察觉参数用错。
    """
    for n in names:
        v = p.get(n)
        if v is None or (isinstance(v, str) and v.strip() == ""):
            raise ToolParamError(
                "缺少必填参数 %s。注意：本工具参数名就是 %s（请先用 get_tool_params 核对准确参数名，"
                "不要臆造 path / file 等别名）" % (n, n)
            )
    return True


# ---------- 结果 JSON 体积上限 ----------
# 各工具返回的 JSON 序列化后不得超过该字符数（默认 10 万，可在 runtime.yaml 的
# limits.max_json_chars 覆盖）。超限时不截断，而是返回参数错误并提示 AI 缩小范围，
# 避免把不完整的结果喂给 AI 导致误判。
DEFAULT_MAX_JSON_CHARS = 100000


def max_json_chars():
    """读取配置中 limits.max_json_chars；未配置时返回默认值。"""
    # 配置文件读取统一走 yaml_utils.load_config_dict，避免多处重复实现
    data = yaml_utils.load_config_dict()
    v = (data.get("limits") or {}).get("max_json_chars")
    if v is None:
        return DEFAULT_MAX_JSON_CHARS
    try:
        v = int(v)
    except (TypeError, ValueError):
        return DEFAULT_MAX_JSON_CHARS
    return v if v > 0 else DEFAULT_MAX_JSON_CHARS


def dump_len(obj):
    """对象序列化为 JSON 后的字符数（无法序列化时按极大值处理）。"""
    try:
        return len(json.dumps(obj, ensure_ascii=False))
    except Exception:
        return 10 ** 12


def enforce_size_limit(result, guidance, max_chars=None):
    """校验工具结果的 JSON 体积；超限时返回错误，提示 AI 缩小范围后重试。

    - 不截断：宁可报错，也不把不完整的结果喂给 AI，避免其据此做出错误判断。
    - guidance：针对该工具的收敛建议（如缩小搜索范围 / 分段读取）。
    - 未超限时原样返回 result；超限时抛 ToolParamError（服务端归类为 parameter，
      提示 AI 这是调用范围问题，应调整参数而非修改工具代码）。
    """
    limit = max_chars if max_chars is not None else max_json_chars()
    size = dump_len(result)
    if size <= limit:
        return result
    raise ToolParamError(
        "结果体积约 %d 字符，超过上限 %d 字符。%s" % (size, limit, guidance)
    )
