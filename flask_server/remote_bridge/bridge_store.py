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

import runtime

# 桥接配置文件与去重记录文件都放在服务目录下
BRIDGE_CONFIG_PATH = runtime.APP_DIR / "remote_bridge.yaml"
BRIDGE_STATE_PATH = runtime.APP_DIR / "remote_bridge_state.json"

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
        # Markdown 复制按钮选择器：AI 回复完成后点它，截获带格式的原文，
        # 推送 QQ 时优先用它。留空则关闭该增强，退回纯文本。
        "md_copy_selector": '.ds-virtual-list--printable .ds-virtual-list-visible-items > div:last-child div[role="button"]:has(.ds-cross-fade)',
        "push": {
            "user": True,              # 是否推送用户消息
            "tool": True,              # 是否推送工具消息
            "ai": True,                # 是否推送 AI 消息
            "thinking": False,         # 是否推送思考过程（默认不推）
        },
        "commands": [],                # 指令列表：{name, label, action, arg}
    }


def _read_yaml():
    """读取 remote_bridge.yaml；文件不存在或解析失败返回空字典。"""
    if not BRIDGE_CONFIG_PATH.exists():
        return {}
    try:
        import yaml
        text = BRIDGE_CONFIG_PATH.read_text(encoding="utf-8")
        return yaml.safe_load(text) or {}
    except Exception as e:
        print("[bridge] 读取 remote_bridge.yaml 失败：", e)
        return {}


def _write_yaml(cfg):
    """写回 remote_bridge.yaml；成功返回 True。"""
    try:
        import yaml
        with open(BRIDGE_CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
        return True
    except Exception as e:
        print("[bridge] 写回 remote_bridge.yaml 失败：", e)
        return False


# 内存中的配置缓存：避免每次读盘
_CONFIG = None


def load_config():
    """读取桥接配置并与默认值合并；结果缓存到内存。"""
    global _CONFIG
    with _lock:
        raw = _read_yaml()
        cfg = _default_config()
        # 逐字段合并：文件里有的用文件值，没有的保留默认
        for k in ("enabled", "app_id", "app_secret", "intents", "md_copy_selector"):
            if k in raw:
                cfg[k] = raw[k]
        if isinstance(raw.get("push"), dict):
            cfg["push"].update(raw["push"])
        if isinstance(raw.get("commands"), list):
            cfg["commands"] = raw["commands"]
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
        for k in ("enabled", "app_id", "app_secret", "intents", "md_copy_selector"):
            if k in patch:
                cfg[k] = patch[k]
        if isinstance(patch.get("push"), dict):
            cfg["push"].update(patch["push"])
        if isinstance(patch.get("commands"), list):
            cfg["commands"] = patch["commands"]
        _write_yaml(cfg)
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
        _write_yaml(cfg)
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
        _write_yaml(cfg)
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
