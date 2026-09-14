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

APP_DIR = Path(__file__).resolve().parent
# 规则目录放在项目根（chat-bridge-main/rules），与 skills/ 同级，便于查看与迁移
RULES_DIR = APP_DIR.parent / "rules"
# 优先级元数据文件（放在规则目录内，_ 前缀不会被 *.md 扫描命中）
META_PATH = RULES_DIR / "_meta.json"

NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# 读取优先级：总是 / 按需 / 关闭
PRIORITIES = ["always", "on-demand", "off"]
PRIORITY_LABELS = {"always": "总是", "on-demand": "按需", "off": "关闭"}
DEFAULT_PRIORITY = "on-demand"

# 默认「异常与自愈」规则：System Prompt 中不再包含该段，改由 AI 遇错时按需读取本规则。
DEFAULT_SELF_HEALING_RULE = """# 异常与自愈（self-healing）

工具调用可能失败或返回「成功但明显不对」的结果，请按下面流程处置，不要盲目重试：

1. 若返回「成功: false」，看错误分类 origin：
   - origin=parameter：这是参数问题（缺失/类型错/取值非法）。先调用 get_tool_params 核对该工具的准确参数名，再用正确参数重试；不要去改工具代码。
   - origin=environment：路径/权限问题，确认路径与权限后重试；不要去改工具代码。
   - origin=tool_internal：这是本地工具代码自身缺陷，反复改参数无效。直接走第 3 步自愈。
2. 若返回「成功: true」但结果与你的请求明显不符（例如：你请求的路径 ≠ 返回的 directory、应为空却非空/应为非空却空、参数像被忽略），先怀疑是参数名写错：
   - 立即调用 get_tool_params 核对准确参数名，若你用了别名（如把 target_directory 写成 path），用正确参数名重试即可——这属于 parameter 问题，不是代码缺陷，不要用 hot_reload_fix。
3. 确认为工具代码缺陷（tool_internal）时，执行自愈：
   - 调用 read_tool_source（参数 tool=出问题的工具名）读取其当前源码，定位缺陷函数；
   - 调用 hot_reload_fix（参数 old_str/new_str 或 content）对 tools_impl.py 打补丁，服务会自动热重载，失败会回滚；
   - 热重载完成后，用「原参数」重新调用该工具验证。不要反复改参数。
"""


def ensure_dir():
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    return RULES_DIR


def _path(name):
    return RULES_DIR / (str(name) + ".md")


def valid_name(name):
    return bool(NAME_RE.match(str(name or "")))


def valid_priority(p):
    return str(p or "") in PRIORITIES


# ---------- 优先级元数据 ----------
def _load_meta():
    if not META_PATH.exists():
        return {}
    try:
        data = json.loads(META_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_meta(meta):
    ensure_dir()
    try:
        META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        print("[rules] 写回优先级元数据失败：", e)
        return False


def get_priority(name):
    meta = _load_meta()
    p = meta.get(str(name))
    return p if valid_priority(p) else DEFAULT_PRIORITY


def set_priority(name, priority):
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
    f = _path(name)
    if not f.exists():
        raise FileNotFoundError("规则不存在：%s" % name)
    return f.read_text(encoding="utf-8", errors="replace")


def write_rule(name, content, priority=None):
    name = str(name or "").strip()
    if not valid_name(name):
        raise ValueError("规则名非法（仅允许字母、数字、下划线、连字符）：%s" % name)
    ensure_dir()
    _path(name).write_text(content or "", encoding="utf-8")
    if priority is not None and valid_priority(priority):
        set_priority(name, priority)
    return name


def delete_rule(name):
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


def seed_defaults():
    """首次启动（规则目录为空）时写入默认 self-healing 规则，并设置默认优先级。"""
    ensure_dir()
    if not list_rules():
        write_rule("self-healing", DEFAULT_SELF_HEALING_RULE, priority="always")
