"""自定义工具（来自标准 skill）—— 技能文档读写

职责：设置页「技能」区块对 SKILL.md 等技能内文档的读取与写回。

- read_skill_doc(skill, rel)：读取技能内某个文档的文本
- write_skill_doc(skill, rel, text)：写回技能内某个文档

安全约束与 read_skill 工具一致：skill 名必须是 skills/ 下的单层目录名，
rel 必须是该技能目录内的相对路径，解析后仍须落在该技能目录内，
防止用 ../ 越出技能目录或写到工程其它位置。
"""
from tool_helpers import SKILLS_ROOT, ToolParamError, _require_single_dir_name


# 允许读写文档的最大字符数：技能说明属手写文档，正常不会超过此量级。
# 上限仅用于挡住异常超大内容，避免界面卡死。
MAX_DOC_CHARS = 200000


def _resolve(skill, rel):
    """把 (skill 名, 技能内相对路径) 解析为绝对路径，并做越界校验。

    - skill 名仅允许单层目录名，防止用 ../ 越出 skills 目录。
    - rel 必须是技能目录内的相对路径，解析后仍须落在该技能目录内。
    """
    skill = _require_single_dir_name(skill)
    rel = str(rel or "").strip()
    if not rel:
        raise ToolParamError("缺少文件相对路径（技能目录内，如 SKILL.md）")
    base = (SKILLS_ROOT / skill).resolve()
    if not base.is_dir():
        raise ToolParamError("技能不存在：%s" % skill)
    target = (base / rel).resolve()
    # 越界校验：解析后的目标路径必须仍在技能目录内
    if base != target and base not in target.parents:
        raise ToolParamError("文件越出技能目录：%s" % rel)
    return target


def read_skill_doc(skill, rel):
    """读取技能内某个文档的文本；文件不存在抛 ToolParamError。"""
    target = _resolve(skill, rel)
    if not target.is_file():
        raise ToolParamError("文件不存在：%s" % rel)
    text = target.read_text(encoding="utf-8", errors="replace")
    return {"skill": skill, "file": rel, "text": text, "path": str(target)}


def write_skill_doc(skill, rel, text):
    """写回技能内某个文档；父目录不存在时自动创建。

    写入内容为纯文本（UTF-8）。返回写入后的字符数与绝对路径。
    """
    target = _resolve(skill, rel)
    text = "" if text is None else str(text)
    if len(text) > MAX_DOC_CHARS:
        raise ToolParamError("内容过长（%d 字符，上限 %d）" % (len(text), MAX_DOC_CHARS))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return {"skill": skill, "file": rel, "chars": len(text), "path": str(target)}
