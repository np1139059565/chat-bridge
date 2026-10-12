"""自定义工具（来自标准 skill）—— 技能级状态与发现

技能（skill）是一等实体，自身带独立的上下线开关，不再由「有没有已上线的
工具」倒推——否则没有工具的技能永远无法上线（历史缺陷）。本模块集中技能级逻辑：

- 技能开关的读写：runtime.yaml 的 skills 分区（不入库，随本机状态变）。
- 技能发现：项目 skills 根下的全部子目录 ∪ 已安装工具所属的技能名。
- 技能上线判定：显式开关优先；从未设置过的技能沿用旧口径（有已上线工具即上线），
  以此保证升级后既有技能状态不突变，同时允许无工具技能被显式打开。
- 技能说明提取：tool.json 顶层 prompt 字段优先，缺失时取 SKILL.md 正文首段。

与工具级状态（custom_tools 分区的 enabled）解耦：工具开关只管工具能否被调用，
技能开关只管技能本身是否挂出（注入说明、出现在技能清单）。
"""
import json
from pathlib import Path

import config_file
import paths

from .paths import resolve_to_abs

# runtime.yaml 中承载技能开关的分区名
SECTION = "skills"


def load_skill_state():
    """读取全部技能开关：{ 技能名: 布尔 }。从未设置过的技能不出现在结果里。"""
    section = config_file.get_runtime_section(SECTION)
    enabled = section.get("enabled") or {}
    return {name: bool(v) for name, v in enabled.items()}


def save_skill_state(state):
    """写回全部技能开关；成功返回 True。"""
    return config_file.update_runtime_section(SECTION, {"enabled": dict(state)})


def set_skill_state(name, enabled):
    """设置单个技能的开关并落盘；成功返回 True。"""
    state = load_skill_state()
    state[name] = bool(enabled)
    return save_skill_state(state)


def _has_enabled_tool(name):
    """该技能下是否至少有一个已上线工具（旧口径，用于未显式设置时的兜底）。"""
    # 延迟导入，避免 registry 与本模块形成导入环
    from .registry import load_tools
    for t in load_tools().values():
        if (t.get("skill_name") or "") == name and t.get("enabled"):
            return True
    return False


def is_skill_online(name):
    """判断技能是否上线。

    显式开关优先；从未设置过开关的技能沿用旧口径：只要有一个已上线工具即视为
    上线。这样升级后既有技能状态与过去一致，无工具技能又可被显式打开。
    """
    state = load_skill_state()
    if name in state:
        return bool(state[name])
    return _has_enabled_tool(name)


def skill_dir_map():
    """返回 { 技能名: 技能目录绝对路径 }。

    来源合并：项目 skills 根下的全部子目录（覆盖无工具技能），以及已安装工具
    所属技能（可能来自其它扫描根）。同名以项目目录优先。
    """
    out = {}
    root = paths.SKILLS_ROOT
    if root.is_dir():
        for d in sorted(root.iterdir(), key=lambda x: x.name):
            if d.is_dir() and not d.name.startswith("."):
                out[d.name] = d
    try:
        from .registry import load_tools
        for t in load_tools().values():
            name = (t.get("skill_name") or "").strip()
            stored = (t.get("skill_dir") or "").strip()
            if name and name not in out and stored:
                out[name] = resolve_to_abs(stored)
    except Exception:
        pass
    return out


def online_skill_names():
    """返回当前处于上线状态的技能名集合（含无工具的技能）。"""
    return {name for name in skill_dir_map() if is_skill_online(name)}


def _first_paragraph(text):
    """取正文首个段落：跳过 YAML front matter 与 Markdown 标题行，遇空行收束。"""
    lines = text.splitlines()
    i = 0
    # 跳过以 --- 包裹的 YAML front matter，避免把元数据当成正文
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        i += 1
    buf = []
    for line in lines[i:]:
        s = line.strip()
        if not s:
            if buf:
                break
            continue
        if s.startswith("#"):
            continue
        buf.append(s)
    return " ".join(buf).strip()


def skill_prompt(name, d):
    """提取技能的说明文字：tool.json 顶层 prompt 优先，否则取 SKILL.md 正文首段。"""
    if not d:
        return ""
    base = Path(d)
    tf = base / "tool.json"
    if tf.is_file():
        try:
            spec = json.loads(tf.read_text(encoding="utf-8"))
            if isinstance(spec, dict):
                p = (spec.get("prompt") or "").strip()
                if p:
                    return p
        except Exception:
            pass
    for fn in ("SKILL.md", "README.md"):
        f = base / fn
        if f.is_file():
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            para = _first_paragraph(text)
            if para:
                return para
    return ""
