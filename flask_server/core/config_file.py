"""
配置文件的统一读写 —— 分区合并版本

配置集中为两份文件，按「是否入库」划分（git 只能整文件忽略，故运行时必须独立）：
- definition.yaml  全部定义，入库（站点映射、工具定义、指令、选择器、主机地址）
- runtime.yaml     全部运行时与密钥，不入库（开关、端口、QQ 凭证、工具上下线）

两份文件内各含三个分区，各子系统各写各段：
- app          主配置（flask / limits / site_profiles / tools）
- custom_tools 自定义工具
- bridge       远程桥接

保存时先读全文件、只替换自己那一段，避免覆盖其它分区的内容。
"""
import os
from pathlib import Path

import paths
import app_log

# 两份合并后的配置文件路径。
# 支持用环境变量 CHAT_BRIDGE_CONFIG_DIR 覆盖配置目录：
# 供测试把读写重定向到临时目录，避免触碰真实配置。
_CFG_DIR_ENV = "CHAT_BRIDGE_CONFIG_DIR"
_cfg_dir_override = os.environ.get(_CFG_DIR_ENV)
if _cfg_dir_override:
    _cfg_dir = Path(_cfg_dir_override).resolve()
    DEFINITION_PATH = _cfg_dir / "definition.yaml"
    RUNTIME_PATH = _cfg_dir / "runtime.yaml"
else:
    DEFINITION_PATH = paths.DEFINITION_PATH
    RUNTIME_PATH = paths.RUNTIME_PATH

# 三个分区名（保持稳定，供各子系统按名读写）
SECTIONS = ("app", "custom_tools", "bridge")


def _load(path):
    """读取一个分区配置文件为字典；文件缺失或解析失败返回空字典。"""
    try:
        import yaml
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        app_log.warn("[config_file]", "读取 %s 失败：%s" % (path.name, e))
        return {}


def _save(path, data):
    """写回一个分区配置文件；成功返回 True。"""
    try:
        import yaml
        # newline="\n"：禁用 Python 的换行翻译。Windows 上 write_text 默认
        # newline=None，会把 \n 翻成 \r\n，写出的配置即 CRLF，与仓库/工作区
        # 要求的 LF 冲突，导致 git 反复把该文件标成 modified（假改动）。
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8", newline="\n")
        return True
    except Exception as e:
        app_log.warn("[config_file]", "写入 %s 失败：%s" % (path.name, e))
        return False


def load_definition():
    """读取全部定义（definition.yaml）为字典。"""
    return _load(DEFINITION_PATH)


def load_runtime():
    """读取全部运行时与密钥（runtime.yaml）为字典。"""
    return _load(RUNTIME_PATH)


def get_definition_section(name):
    """取定义文件里的某个分区；不存在返回空字典。"""
    return (_load(DEFINITION_PATH).get(name) or {})


def get_runtime_section(name):
    """取运行时文件里的某个分区；不存在返回空字典。"""
    return (_load(RUNTIME_PATH).get(name) or {})


def update_definition_section(name, data):
    """更新定义文件里的某个分区，保留其它分区；成功返回 True。"""
    store = _load(DEFINITION_PATH)
    store[name] = data
    return _save(DEFINITION_PATH, store)


def update_runtime_section(name, data):
    """更新运行时文件里的某个分区，保留其它分区；成功返回 True。"""
    store = _load(RUNTIME_PATH)
    store[name] = data
    return _save(RUNTIME_PATH, store)
