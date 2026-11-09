"""
客户端注册表 —— 注册信息的持久化读写

职责：
1. 把客户端提交的注册信息（客户端标识 / 自定义配置 / 可执行指令声明）
   以 JSON 原样落盘，服务重启后仍在；
2. 提供登记、取回、注销三个原语，供路由层调用。

设计边界：
- 自定义配置不校验、不清洗、不解释字段：存进去什么，取出来就是什么；
- 落盘用标准 JSON，原生保留嵌套对象、数组、null、空字符串、中文与特殊字符；
- 落盘位置取 paths.DATA_DIR（运行时数据目录），该目录已被 .gitignore 忽略，
  客户端私有数据不入库、不污染版本库；
- 每次操作都重新读盘，不设进程内缓存，重启后仍读到同一份数据。
"""
import json
from pathlib import Path

import paths  # 路径基准：导入即把 core/ 与 tools/ 加入模块搜索路径
import app_log

# 注册信息落盘文件：运行时数据目录下的独立 JSON 文件。
# 定义成模块级变量，测试可覆盖它把写盘重定向到临时目录，不触碰真实数据。
REGISTRY_PATH = paths.DATA_DIR / "client_registry.json"


def _read_store():
    """从磁盘读出整张注册表；文件缺失或内容损坏时按空表处理。"""
    # 文件不存在表示尚未有任何客户端注册，返回空字典。
    if not Path(REGISTRY_PATH).exists():
        return {}
    try:
        # 按 UTF-8 还原任意字符；json.load 保留对象/数组/null 的原生类型。
        with open(str(REGISTRY_PATH), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        # 顶层必须是对象，否则无法按 site_key 索引，按空表兜底。
        return data if isinstance(data, dict) else {}
    except Exception as e:
        # 读取失败不阻断请求，记录原因便于排查，按空表处理。
        app_log.warn("[client_registry]", "读取注册表失败：%s" % e)
        return {}


def _write_store(store):
    """把整张注册表写回磁盘；成功返回 True。"""
    # 父目录可能尚未创建（首次注册），先补齐。
    Path(REGISTRY_PATH).parent.mkdir(parents=True, exist_ok=True)
    # newline 用 LF：Windows 上禁用换行翻译，避免写出 CRLF 造成假改动。
    with open(str(REGISTRY_PATH), "w", encoding="utf-8", newline="\n") as fh:
        # ensure_ascii=False：中文与特殊字符按原字符写入，不转成转义序列。
        json.dump(store, fh, ensure_ascii=False, sort_keys=False, indent=2)
    return True


def register(site_key, custom_config, commands):
    """登记一个客户端；同一 site_key 重复注册时整条覆盖，不追加。"""
    # 读出现有整表，保留其它客户端的条目。
    store = _read_store()
    # 自定义配置与指令声明直接作为值存入，不校验字段、不清洗结构、不解释语义。
    store[site_key] = {
        "site_key": site_key,
        "custom_config": custom_config,
        "commands": commands,
    }
    # 整表写回：一次落盘完成覆盖，无需先删后加。
    _write_store(store)
    return store[site_key]


def lookup(site_key):
    """按客户端标识取回注册条目；未注册返回 None。"""
    # 每次从磁盘读，进程重启后同样能取回。
    store = _read_store()
    return store.get(site_key)


def unregister(site_key):
    """移除一个客户端登记；标识不存在时静默返回 False，不报错。"""
    store = _read_store()
    # 不存在的键直接判否，不抛异常。
    if site_key not in store:
        return False
    del store[site_key]
    _write_store(store)
    return True
