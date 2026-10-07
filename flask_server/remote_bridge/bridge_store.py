"""远程桥接 —— 配置与去重记账存储

职责：
1. 读写 remote_bridge.yaml：QQ 凭证、推送开关、指令列表
2. 维护「已推送消息 id 集合」并持久化，按会话隔离

设计说明：
- 配置与工具服务既有的 config.yaml 分离，独立成 remote_bridge.yaml，
  避免把 QQ 凭证与工具开关混在一起。
- 已推送集合必须持久化：sendPage 每次推送全量切片，若不记账，
  服务重启后会把历史消息全量复推、刷屏用户手机。
- 所有写操作都加锁，桥接层可能在 WebSocket 回调线程与 Flask 请求线程
  中同时读写。
"""
import json
import threading
from pathlib import Path

import paths
import runtime
import config_file

# 路径说明：
#   definition.yaml / runtime.yaml —— 桥接配置集中在两份合并文件的 bridge 分区，见下
#   remote_bridge_state.json      —— 已推送去重记账，运行时产物，不入库
BRIDGE_STATE_PATH = paths.BRIDGE_STATE_PATH

# 桥接配置集中在两份合并文件的 bridge 分区（见 core/config_file.py）：
#   definition.yaml 的 bridge —— 定义（入库）：指令、选择器、订阅事件位
#   runtime.yaml 的 bridge    —— 运行时与密钥（不入库）：开关、凭证、推送开关
# 密钥字段：与运行时同写 runtime.yaml（不入库）
SECRET_KEYS = ("app_id", "app_secret")
# 定义字段：写 definition.yaml 的 bridge 分区（入库，换机器应保留）
#   command_params：内置指令的参数（键为指令名不带 /，如 {"md": {"selector": "..."}}）。
#   md_selector 为旧字段，保留在兼容列表里，读取时归并进 command_params。
SETTING_KEYS = ("intents", "md_selector", "command_params", "commands")
# 运行时字段：写 runtime.yaml 的 bridge 分区（不入库，随本机状态变）
RUNTIME_KEYS = ("enabled", "push")

# 用可重入锁：save_config 持锁期间会调用 get_config()，
# 后者在未初始化时会进入 load_config() 再取同一把锁。
# 普通 Lock 会在此自锁死，故必须用 RLock。
_lock = threading.RLock()

# 推送开关默认值：三类消息都推，思考过程默认不推
def _default_config():
    """返回桥接配置的默认值。"""
    return {
        "enabled": True,               # 桥接总开关，默认开启（远程功能开箱即用）
        "app_id": "",                  # QQ 机器人 AppID
        "app_secret": "",              # QQ 机器人 AppSecret
        "intents": 0,                 # 订阅的事件位；0 表示用代码里的默认值（单聊）
        "push": {
            "user": True,              # 是否推送用户消息
            "tool": True,              # 是否推送工具消息
            "ai": True,                # 是否推送 AI 消息
            "thinking": False,         # 是否推送思考过程（默认不推）
            # 语音识别开关：关时收到语音文件直接丢弃，不进 ASR；
            # 开时语音经识别转文字、回发等 /vo 确认后才投给 AI。默认关。
            "voice": False,
            # 质量检测开关：与推送开关同区存放，供前端设置页读写。
            # 默认全开；显式关时对应检测不跑。字段在此列出，避免读写时丢键。
            "check_code_only": True,
            "check_thinking": True,
            "check_multi_call": True,
            "check_memory": True,
            # 记忆检查的轮次间隔（默认 20 轮），可在设置页调整；下限 1。
            "check_memory_interval": 20,
        },
        # 内置指令的通用参数：键为指令名（不带 /），值为该指令的参数字典。
        # 让「内置指令需要配置」走统一机制，而非给某条指令单独开输入框。
        # 目前只有 /md：selector 是 Markdown 复制按钮选择器，留空则关闭格式增强。
        "command_params": {
            "md": {
                "selector": '.ds-virtual-list--printable .ds-virtual-list-visible-items > div:last-child div[role="button"]:has(.ds-cross-fade)',
            },
        },
        # 指令列表：{name, label, selector, page_url} 或组合指令 {name, label, steps, interval}
        "commands": [],
    }


def _read_merged():
    """读取合并文件中 bridge 分区的定义段与运行时段，合并为一个配置字典。

    字段分两类落盘（均在合并文件的 bridge 分区内）：
      定义   -> definition.yaml（入库，如指令、选择器、订阅事件位）
      运行时 -> runtime.yaml（不入库，如凭证、总开关、推送开关）
    """
    settings = config_file.get_definition_section("bridge")
    runtime_cfg = config_file.get_runtime_section("bridge")
    merged = dict(settings)
    merged.update(runtime_cfg)
    return merged


def _write_split(cfg):
    """把 bridge 配置按「定义 / 运行时」分写到两份合并文件的分区。"""
    settings = {k: v for k, v in cfg.items() if k in SETTING_KEYS}
    runtime_cfg = {k: v for k, v in cfg.items() if k in RUNTIME_KEYS or k in SECRET_KEYS}
    ok1 = config_file.update_definition_section("bridge", settings)
    ok2 = config_file.update_runtime_section("bridge", runtime_cfg)
    return bool(ok1 and ok2)


# 内存中的配置缓存：避免每次读盘
_CONFIG = None


def load_config():
    """读取桥接配置并与默认值合并；结果缓存到内存。"""
    global _CONFIG
    with _lock:
        raw = _read_merged()
        cfg = _default_config()
        # 逐字段合并：文件里有的用文件值，没有的保留默认
        for k in ("enabled", "app_id", "app_secret", "intents"):
            if k in raw:
                cfg[k] = raw[k]
        # 内置指令参数：以默认值为基底逐指令、逐键合并，文件值优先
        if isinstance(raw.get("command_params"), dict):
            for cmd, params in raw["command_params"].items():
                if isinstance(params, dict):
                    cfg["command_params"].setdefault(cmd, {}).update(params)
        # 兼容旧字段 md_selector：归并进 command_params.md.selector（新字段未设时才用）
        if raw.get("md_selector") and not (cfg["command_params"].get("md") or {}).get("selector"):
            cfg["command_params"].setdefault("md", {})["selector"] = raw["md_selector"]
        if isinstance(raw.get("push"), dict):
            cfg["push"].update(raw["push"])
        if isinstance(raw.get("commands"), list):
            # 按命令名合并：文件里的指令优先，默认指令里未出现的补进来。
            # 直接用文件列表覆盖会让默认的 /md 被空列表清掉；
            # 用户删掉某条默认指令后又会「复活」——因此以文件为准，
            # 只补从未在文件里出现过的默认项。
            user = raw["commands"]
            seen = set()
            for c in user:
                if isinstance(c, dict) and c.get("name"):
                    seen.add(str(c["name"]).lower())
            merged = list(user)
            for d in cfg.get("commands") or []:
                if str(d.get("name", "")).lower() not in seen:
                    merged.append(d)
            cfg["commands"] = merged
        _CONFIG = cfg
        return cfg


def get_config():
    """取当前配置（带缓存）。"""
    if _CONFIG is None:
        return load_config()
    return _CONFIG


def save_config(patch):
    """部分更新配置并落盘。patch 为要覆盖的字段字典。返回更新后的完整配置。"""
    global _CONFIG
    with _lock:
        cfg = get_config()
        for k in ("enabled", "app_id", "app_secret", "intents"):
            if k in patch:
                cfg[k] = patch[k]
        # 内置指令参数：逐指令、逐键合并（patch 只覆盖给到的键，不整体替换）
        if isinstance(patch.get("command_params"), dict):
            for cmd, params in patch["command_params"].items():
                if isinstance(params, dict):
                    cfg["command_params"].setdefault(cmd, {}).update(params)
        # 兼容旧字段：写入 command_params.md.selector
        if "md_selector" in patch:
            cfg["command_params"].setdefault("md", {})["selector"] = patch["md_selector"]
        if isinstance(patch.get("push"), dict):
            cfg["push"].update(patch["push"])
        if isinstance(patch.get("commands"), list):
            cfg["commands"] = patch["commands"]
        # 分写：密钥进密钥文件（不入库），其余进设置文件（入库）
        _write_split(cfg)
        _CONFIG = cfg
        return cfg


# ---------- 已推送消息 id 集合 ----------
def _read_state():
    """读取去重状态文件；不存在或损坏返回空结构。"""
    if not BRIDGE_STATE_PATH.exists():
        return {}
    try:
        return json.loads(BRIDGE_STATE_PATH.read_text(encoding="utf-8")) or {}
    except Exception as e:
        print("[bridge] 读取去重状态失败：", e)
        return {}


def _write_state(state):
    """写回去重状态文件。"""
    try:
        BRIDGE_STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print("[bridge] 写回去重状态失败：", e)


# 去重集合的内存缓存：{ 会话 id: set(消息 id) }
_pushed = None


def _ensure_pushed_loaded():
    """惰性加载去重集合到内存。"""
    global _pushed
    if _pushed is not None:
        return
    state = _read_state()
    _pushed = {}
    for conv_id, ids in (state.get("pushed") or {}).items():
        _pushed[conv_id] = set(ids or [])


def list_commands():
    """读取指令列表（返回副本）。"""
    with _lock:
        return list(get_config().get("commands") or [])


def upsert_command(index, entry):
    """新增或更新一条指令。

    index 为 None 时追加；否则替换该下标的指令（用于「修改」）。
    @param index 指令下标或 None
    @param entry 指令对象 {name, label, selector, page_url}
    @returns 更新后的完整指令列表
    """
    with _lock:
        cfg = get_config()
        cmds = list(cfg.get("commands") or [])
        if index is None:
            cmds.append(entry)
        elif 0 <= index < len(cmds):
            cmds[index] = entry
        else:
            raise IndexError("指令下标越界")
        cfg["commands"] = cmds
        _write_split(cfg)
        _CONFIG = cfg
        return list(cmds)


def remove_command(index):
    """按下标删除一条指令，返回更新后的列表。"""
    with _lock:
        cfg = get_config()
        cmds = list(cfg.get("commands") or [])
        if not (0 <= index < len(cmds)):
            raise IndexError("指令下标越界")
        cmds.pop(index)
        cfg["commands"] = cmds
        _write_split(cfg)
        _CONFIG = cfg
        return list(cmds)


def get_pushed_set(conv_id):
    """取某会话已推送的消息 id 集合（返回副本，避免外部误改）。"""
    with _lock:
        _ensure_pushed_loaded()
        return set(_pushed.get(conv_id or "__default__", set()))


def mark_pushed(conv_id, msg_ids):
    """把一组消息 id 记入某会话的已推送集合，并持久化。"""
    with _lock:
        _ensure_pushed_loaded()
        key = conv_id or "__default__"
        bucket = _pushed.setdefault(key, set())
        for mid in msg_ids or []:
            if mid:
                bucket.add(mid)
        # 落盘：把 set 转成 list 以便 JSON 序列化
        state = {"pushed": {k: sorted(v) for k, v in _pushed.items()}}
        _write_state(state)


# ---------- 待推消息缓存（推送失败后重试） ----------
# 用途：某条消息推送失败（窗口关闭 / 网络错误）时暂存于此，下次上报时优先重试。
# 解决：一条消息推送失败后若滚出网页可见区，就不再出现在上报切片里，
#       没有这份缓存就永远推不到（表现为「最后一轮被漏、下次才补」）。
# 仅存内存：进程重启即清空，可接受——重启后抽屉会重新上报全量切片，
#          且窗口正常时消息本就会推成功。
_pending_msgs = {}


def merge_pending(conv_id, messages):
    """把待推消息并入当前上报切片：当前切片优先（字段更新），待推里独有的补到末尾。

    调用方：message_router.handle_report 在推送前合并，使失败过的消息获得重试机会。
    @param conv_id 会话 id
    @param messages 当前上报的消息切片（有序）
    @returns 合并后的消息列表
    """
    key = conv_id or "__default__"
    with _lock:
        pend = dict(_pending_msgs.get(key) or {})
    if not pend:
        return list(messages)
    seen = set()
    out = []
    for m in messages or []:
        mid = (m or {}).get("id") or ""
        if mid:
            seen.add(mid)
        out.append(m)
    for mid, m in pend.items():
        if mid not in seen:
            out.append(m)
    return out


def set_pending(conv_id, failed_messages):
    """用本轮失败的消息替换该会话的待推缓存（成功 / 跳过的消息随之移出）。

    @param conv_id 会话 id
    @param failed_messages 本轮推送失败的消息对象列表
    """
    key = conv_id or "__default__"
    with _lock:
        _pending_msgs[key] = {(m or {}).get("id"): m for m in (failed_messages or []) if (m or {}).get("id")}
