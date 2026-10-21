"""文件访问权限策略

职责：判定某个路径是否允许被工具访问，并按「读 / 写」区分严格程度。

为什么集中在此：
    文件类工具（read_file / write_to_file / replace_in_file / delete_file 等）
    此前对路径完全不设限，权限一收紧就只能改多处代码。集中一处后，
    策略调整只改本文件，各工具只需在解析路径时调用 check_path。

四档策略（对应配置 permissions.file_access）：
    project         仅工程目录；最严
    project_whitelist 工程目录 + 用户指定的白名单目录（默认档）
    all_readonly    全盘可读，写仍限工程目录
    all             完全放开（历史行为）

设计约束：
    本模块只做判定，不抛工具框架的异常——它不认识 ToolParamError，
    否则会与 tool_helpers 形成循环导入。调用方捕获 PathDenied 后自行转换。
"""
import os

import paths


class PathDenied(Exception):
    """路径被权限策略拒绝。调用方应转换为工具参数错误。"""


# 四档策略的合法取值
MODES = ("project", "project_whitelist", "all_readonly", "all")
# 默认档：完全放开。与历史行为一致，避免升级后功能突然不可用。
DEFAULT_MODE = "all"


def _cfg():
    """取权限配置；未配置时返回默认档。

    延迟导入 runtime：runtime 在启动时才填充配置，且它自身导入 paths，
    顶层导入本模块会过早固定引用。
    """
    try:
        import runtime
        return (runtime.CONFIG.get("permissions") or {})
    except Exception:
        return {}


def current_mode():
    """取当前生效的策略档位；非法值回退默认档。"""
    mode = str(_cfg().get("file_access") or DEFAULT_MODE).strip()
    return mode if mode in MODES else DEFAULT_MODE


def _norm(p):
    """规范化为可比较的绝对路径（统一大小写，Windows 盘符不敏感）。"""
    return os.path.normcase(os.path.abspath(str(p)))


def _under(target, base):
    """判断 target 是否位于 base 之下（含 base 自身）。

    用 commonpath 而非字符串前缀：后者会把 C:\\ab 误判为在 C:\\a 之下。
    """
    try:
        return os.path.commonpath([_norm(target), _norm(base)]) == _norm(base)
    except ValueError:
        # 跨盘符：commonpath 抛错，视为不在其下
        return False


def _whitelist():
    """取白名单目录列表；非法项忽略。"""
    raw = _cfg().get("whitelist_dirs") or []
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def check_path(target, write=False):
    """判定路径是否允许访问；不允许则抛 PathDenied。

    @param target 已解析的绝对路径
    @param write  是否为写操作（写操作比读更严）
    @raises PathDenied 拒绝访问时抛出，消息可直接展示给用户/AI
    """
    mode = current_mode()
    # 完全放开：不做任何检查
    if mode == "all":
        return
    root = paths.PROJECT_ROOT
    # 工程目录内：无论哪档都允许
    if _under(target, root):
        return
    # 全盘只读：读放行，写拒绝
    if mode == "all_readonly":
        if not write:
            return
        raise PathDenied(
            "当前权限为「全盘只读」：只能写入工程目录内的文件，拒绝写入 %s。"
            "如需写入，请在设置页把文件访问权限调整为更宽松的档位。" % target)
    # 工程 + 白名单：读写在白名单目录内都允许
    if mode == "project_whitelist":
        for d in _whitelist():
            if _under(target, d):
                return
        raise PathDenied(
            "当前权限为「工程 + 白名单」：%s 不在允许范围内。"
            "如需访问，请在设置页把它加入白名单目录，或调整文件访问权限档位。" % target)
    # 仅工程目录
    raise PathDenied(
        "当前权限为「仅当前项目」：只允许访问工程目录内的文件，拒绝访问 %s。"
        "如需访问，请在设置页调整文件访问权限档位。" % target)
