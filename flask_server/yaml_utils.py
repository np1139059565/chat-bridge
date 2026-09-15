"""
AI 工具调用镜像插件 —— YAML 处理公共原语

本模块集中存放 config.yaml 与 custom_tools.yaml 两套受限解析器共用的底层函数：
- coerce_scalar：把 YAML 标量字符串转成 Python 值（bool / int / float / str / None）
- strip_comment：去掉行内注释，但保留引号内的 #
- quote：把 Python 字符串安全地写成带引号的 YAML 标量
- load_config_dict：读取 flask_server/config.yaml 为字典（各工具读取配置的统一入口）

两个 YAML 文件各自的结构（块映射 / 工具列表）差异较大，其整体解析器仍保留在
各自模块内；此处只合并真正重复的标量级处理与配置文件读取，避免同一逻辑多处维护。
"""
from pathlib import Path

# config.yaml 位于本文件同目录（flask_server/）
CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def load_config_dict():
    """读取 config.yaml 并返回字典；文件缺失、无 PyYAML 或解析失败时返回 {}。

    这是各工具读取配置的统一入口（如 limits.max_json_chars、tools.run_command.languages）。
    """
    try:
        import yaml
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
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
