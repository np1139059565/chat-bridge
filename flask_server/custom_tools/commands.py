"""自定义工具（来自标准 skill）—— 外部指令视图

职责：把已上线 skill 在 tool.json 的 commands 字段里声明的指令，汇总为
可供指令面板查询的清单。外部指令不由宿主执行，而是映射到一个 external
工具，交由该工具的提供方（扩展）自己轮询执行；宿主只做「目录 + 转接器」。

生效条件与工具一致：该 skill 至少有一个工具处于上线状态。
"""
import json

from .registry import load_tools
from .paths import resolve_to_abs


def _online_skill_dirs():
    """返回已上线 skill 的 {skill_name: skill_dir}。

    判定口径与工具一致：只要该 skill 有任一工具 enabled，即视为上线。
    skill_dir 存的是项目根相对路径，调用方按需再用 resolve_to_abs 还原。
    """
    out = {}
    for t in load_tools().values():
        if not t.get("enabled"):
            continue
        name = (t.get("skill_name") or "").strip()
        d = (t.get("skill_dir") or "").strip()
        if name and d:
            out[name] = d
    return out


def _load_spec(skill_dir):
    """读取某 skill 目录下 tool.json 的原始 JSON；失败返回 None。

    读取失败（文件缺失 / JSON 非法）不应中断指令汇总，跳过该 skill 即可。
    """
    tf = skill_dir / "tool.json"
    if not tf.exists():
        return None
    try:
        return json.loads(tf.read_text(encoding="utf-8"))
    except Exception as e:
        print("[custom_tools] 读取外部指令失败：", tf, e)
        return None


def _collect_from_spec(spec, skill, tools):
    """从单个 skill 的 tool.json 规格里抽取合法指令项，返回列表。

    合法性判定（不合法则跳过该条，不报错，避免一条坏声明拖垮全部）：
      1. 是对象；2. name 以 / 开头；3. tool 映射到本 skill 已上线的工具。
    映射目标必须存在且上线，否则指令按了也没人执行，不如不列。
    """
    out = []
    for c in (spec.get("commands") or []):
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "").strip()
        if not name.startswith("/"):
            continue
        tool = (c.get("tool") or "").strip()
        entry = tools.get(tool)
        # 映射目标必须存在且上线，且属于同一 skill，避免跨 skill 误挂
        if not entry or not entry.get("enabled"):
            continue
        if (entry.get("skill_name") or "") != skill:
            continue
        out.append({
            "name": name,                       # 主命令名（带 /）
            "alias": (c.get("alias") or "").strip(),  # 快捷键（可空）
            "desc": (c.get("desc") or "").strip(),    # 说明
            "tool": tool,                       # 映射的外部工具名
            "params": c.get("params") or {},    # 固定参数，随命令下发
            "provider": entry.get("provider") or "",  # 执行方
            "skill": skill,                     # 所属 skill
        })
    return out


def list_external_commands():
    """汇总所有已上线 skill 的外部指令声明。

    @returns 指令对象列表，每项含 name / alias / desc / tool / params / provider / skill
    """
    tools = load_tools()
    out = []
    for skill, stored in _online_skill_dirs().items():
        spec = _load_spec(resolve_to_abs(stored))
        if not isinstance(spec, dict):
            continue
        out += _collect_from_spec(spec, skill, tools)
    return out


def resolve_external_command(cmd):
    """按主命令名或别名查一条外部指令；未命中返回 None。

    比对统一转小写，与内置指令的别名解析口径保持一致。
    """
    low = (cmd or "").lower()
    for c in list_external_commands():
        if c["name"].lower() == low:
            return c
        if c.get("alias") and c["alias"].lower() == low:
            return c
    return None


def external_command_names():
    """返回全部外部指令的可用名（主名 + 别名，小写），用于冲突提示与帮助。"""
    names = set()
    for c in list_external_commands():
        names.add(c["name"].lower())
        if c.get("alias"):
            names.add(c["alias"].lower())
    return names
