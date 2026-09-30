"""AI 工具调用镜像插件 —— 规则（Rules）文件管理

规则 = 用户自定义的 markdown 约定文件，存放于项目根目录 rules/ 下，每个规则一个 .md 文件。
- 设置页可增 / 删 / 改规则，并为每条规则设置「读取优先级」；
- 优先级取值：always（总是）/ on-demand（按需）/ off（关闭），存于 rules/_meta.json；
- AI 通过工具 list_rules / read_rule 按需读取规则内容（不全部塞进 System Prompt）；
- 优先级写入 System Prompt 的规则列表，由 AI 据此决定何时读取。

文件名即规则名，仅允许 [A-Za-z0-9_-]，扩展名固定 .md。
"""
import json
import re
from pathlib import Path

import paths

# 规则目录统一由 paths 提供（位于工程根，与 skills/ 同级）
RULES_DIR = paths.RULES_DIR
# 优先级元数据文件（放在规则目录内，_ 前缀不会被 *.md 扫描命中）
META_PATH = RULES_DIR / "_meta.json"

NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# 读取优先级：总是 / 按需 / 关闭
PRIORITIES = ["always", "on-demand", "off"]
PRIORITY_LABELS = {"always": "总是", "on-demand": "按需", "off": "关闭"}
DEFAULT_PRIORITY = "on-demand"

def ensure_dir():
    """确保规则目录存在，返回该目录路径。"""
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    return RULES_DIR


def _path(name):
    """由规则名得到对应的 .md 文件路径（不做存在性校验）。"""
    return RULES_DIR / (str(name) + ".md")


def valid_name(name):
    """校验规则名是否合法（仅字母、数字、下划线、连字符）。"""
    return bool(NAME_RE.match(str(name or "")))


def valid_priority(p):
    """校验优先级取值是否在允许集合内。"""
    return str(p or "") in PRIORITIES


# ---------- 优先级元数据 ----------
def _load_meta():
    """读取 _meta.json；文件缺失或格式非法时返回空字典。"""
    if not META_PATH.exists():
        return {}
    try:
        data = json.loads(META_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_meta(meta):
    """写回 _meta.json；失败时打印原因并返回 False。"""
    ensure_dir()
    try:
        META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        print("[rules] 写回优先级元数据失败：", e)
        return False


def get_priority(name):
    """取某条规则的读取优先级；未设置或非法时回退默认值 on-demand。"""
    meta = _load_meta()
    p = meta.get(str(name))
    return p if valid_priority(p) else DEFAULT_PRIORITY


def set_priority(name, priority):
    """设置某条规则的读取优先级；名称或优先级非法时抛 ValueError。"""
    name = str(name or "").strip()
    if not valid_name(name):
        raise ValueError("规则名非法（仅允许字母、数字、下划线、连字符）：%s" % name)
    if not valid_priority(priority):
        raise ValueError("优先级非法（仅允许 %s）：%s" % ("/".join(PRIORITIES), priority))
    meta = _load_meta()
    meta[name] = priority
    _save_meta(meta)
    return priority


def list_rules():
    """列出全部规则，返回 [{name, summary, priority}]，summary 取首个非空行（截断）。"""
    ensure_dir()
    out = []
    for f in sorted(RULES_DIR.glob("*.md")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""
        summary = ""
        for line in text.splitlines():
            s = line.strip().lstrip("#").strip()
            if s:
                summary = s[:120]
                break
        out.append({"name": f.stem, "summary": summary, "priority": get_priority(f.stem)})
    return out


def read_rule(name):
    """读取某条规则的完整内容；文件不存在时抛 FileNotFoundError。"""
    f = _path(name)
    if not f.exists():
        raise FileNotFoundError("规则不存在：%s" % name)
    return f.read_text(encoding="utf-8", errors="replace")


def write_rule(name, content, priority=None):
    """写入（新建或覆盖）某条规则，可选同时更新其优先级；返回规范化后的规则名。"""
    name = str(name or "").strip()
    if not valid_name(name):
        raise ValueError("规则名非法（仅允许字母、数字、下划线、连字符）：%s" % name)
    ensure_dir()
    _path(name).write_text(content or "", encoding="utf-8")
    if priority is not None and valid_priority(priority):
        set_priority(name, priority)
    return name


def delete_rule(name):
    """删除某条规则及其优先级记录；规则文件确实被删除时返回 True。"""
    f = _path(name)
    removed = False
    if f.exists():
        f.unlink()
        removed = True
    meta = _load_meta()
    if str(name) in meta:
        del meta[str(name)]
        _save_meta(meta)
    return removed
