"""
AI 工具调用镜像插件 —— YAML 处理公共原语

本模块集中存放主配置与自定义工具配置两套受限解析器共用的底层函数：
- coerce_scalar：把 YAML 标量字符串转成 Python 值（bool / int / float / str / None）
- strip_comment：去掉行内注释，但保留引号内的 #
- quote：把 Python 字符串安全地写成带引号的 YAML 标量
- load_config_dict：读取主配置（definition.yaml + runtime.yaml 的 app 分区）为字典（各工具读取配置的统一入口）

两个 YAML 文件各自的结构（块映射 / 工具列表）差异较大，其整体解析器仍保留在
各自模块内；此处只合并真正重复的标量级处理与配置文件读取，避免同一逻辑多处维护。
"""
import config_file


def merge_app_sections(base, rt):
    """把 runtime 的 app 分区合并进 definition 的 app 分区（就地修改 base 并返回）。

    合并规则：flask 区块逐字段覆盖；tools 区块逐工具、逐字段覆盖。
    这是 config_store 与 load_config_dict 两处共用的合并核心，避免同一逻辑多处维护。
    @param base definition 的 app 分区字典
    @param rt   runtime 的 app 分区字典；为空时直接返回 base
    @returns 合并后的 base（同一对象）
    """
    # runtime 为空：无需合并，直接返回定义
    if not rt:
        return base
    # flask 区块逐字段合并：运行时覆盖定义中的同名字段
    if isinstance(rt.get("flask"), dict):
        base.setdefault("flask", {})
        base["flask"].update(rt["flask"])
    # tools 区块逐工具合并：运行时覆盖定义中同名工具的字段
    if isinstance(rt.get("tools"), dict):
        base.setdefault("tools", {})
        for name, ent in rt["tools"].items():
            if isinstance(ent, dict):
                base["tools"].setdefault(name, {}).update(ent)
    return base


def load_config_dict():
    """读取主配置（definition.yaml 与 runtime.yaml 的 app 分区）并合并为字典。

    这是各工具读取配置的统一入口（如 limits.max_json_chars、tools.run_command.languages）。
    运行时字段（工具开关、语言清单）覆盖定义中的同名字段，与主配置加载口径一致。
    """
    try:
        base = config_file.get_definition_section("app")
        rt = config_file.get_runtime_section("app")
        # 合并核心委托给公共函数，与 config_store 共用同一实现
        return merge_app_sections(base, rt)
    except Exception:
        return {}


def _unquote(v):
    """若 v 是引号包裹的字符串则去引号并还原转义；否则返回 None。"""
    if len(v) >= 2 and v[0] in ('"', "'") and v[-1] == v[0]:
        return v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return None


def _coerce_number(v):
    """尝试把 v 转为 int（优先）或 float；都不行返回原字符串。"""
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


def coerce_scalar(v):
    """把 YAML 标量字符串转成合适的 Python 值。

    支持的写法：双引号 / 单引号字符串、true/false、null/~ 或空串、整数、浮点数，
    其余情况原样返回字符串。引号内的 \\" 与 \\\\ 会做转义还原。
    """
    v = v.strip()
    # 引号包裹的字符串优先处理（引号内不参与关键字判断）
    unquoted = _unquote(v)
    if unquoted is not None:
        return unquoted
    low = v.lower()
    # 布尔字面量
    if low == "true":
        return True
    if low == "false":
        return False
    # 空值与显式 null 标记
    if low in ("null", "~", ""):
        return None
    # 整数优先，其次浮点，最后原样返回字符串
    return _coerce_number(v)


def strip_comment(s):
    """去掉行首或空白之后的 # 注释，但引号内的 # 不当注释（描述里可能含 #）。"""
    out = []
    in_str = False
    q = ""
    prev = ""
    for ch in s:
        if in_str:
            # 引号字符串内部：原样保留，直到遇到配对的引号
            out.append(ch)
            if ch == q:
                in_str = False
        elif ch in ('"', "'"):
            # 进入引号字符串
            in_str = True
            q = ch
            out.append(ch)
        elif ch == "#" and (prev == "" or prev.isspace()):
            # 位于行首或空白之后的 #：注释起点，截断
            break
        else:
            out.append(ch)
        prev = ch
    return "".join(out).rstrip()


def quote(s):
    """把字符串转义并包上双引号，用于写出 YAML 标量。"""
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    return '"' + s + '"'
