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

# 路径说明（按「是否含密钥」分离，决定谁能入库）：
#   remote_bridge.yaml          —— 仅存 QQ 凭证（app_id / app_secret），含密钥，不入库
#   remote_bridge_settings.yaml —— 存开关、指令等非密钥配置，入库，换机器不丢
#   remote_bridge_state.json    —— 已推送去重记账，运行时产物，不入库
BRIDGE_SECRETS_PATH = runtime.APP_DIR / "remote_bridge.yaml"
BRIDGE_SETTINGS_PATH = runtime.APP_DIR / "remote_bridge_settings.yaml"
BRIDGE_STATE_PATH = runtime.APP_DIR / "remote_bridge_state.json"

# 密钥字段：只写 secrets 文件
SECRET_KEYS = ("app_id", "app_secret")
# 非密钥标量字段：只写 settings 文件
SETTING_SCALAR_KEYS = ("enabled", "intents", "md_selector")

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
        },
        # Markdown 复制按钮选择器：AI 回复完成后点它，截获带格式的原文，
        # 推送 QQ 时优先使用。留空则关闭格式增强，退回纯文本。
        # 对应内置指令 /md（可手动触发一次采集）。
        "md_selector": '.ds-virtual-list--printable .ds-virtual-list-visible-items > div:last-child div[role="button"]:has(.ds-cross-fade)',
        # 指令列表：{name, label, selector, page_url} 或组合指令 {name, label, steps, interval}
        "commands": [],
    }


def _read_yaml(path):
    """读取一个 YAML 文件；不存在或解析失败返回空字典。"""
    if not path.exists():
        return {}
    try:
        import yaml
        text = path.read_text(encoding="utf-8")
        return yaml.safe_load(text) or {}
    except Exception as e:
        print("[bridge] 读取 %s 失败：%s" % (path.name, e))
        return {}


def _write_yaml(path, data):
    """写入一个 YAML 文件；成功返回 True。"""
    try:
        import yaml
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        return True
    except Exception as e:
        print("[bridge] 写入 %s 失败：%s" % (path.name, e))
        return False


def _read_merged():
    """读取密钥文件与设置文件并合并为一个配置字典。

    迁移逻辑：旧版本把凭证与指令混存在 remote_bridge.yaml 一个文件里。
    若发现该文件含非密钥字段（如 commands），把它们搬到设置文件，
    使换机器时指令不再随密钥一起被排除。
    """
    secrets = _read_yaml(BRIDGE_SECRETS_PATH)
    settings = _read_yaml(BRIDGE_SETTINGS_PATH)
    migrated = False
    for k in list(secrets.keys()):
        if k in SECRET_KEYS:
            continue
        if k not in settings:
            settings[k] = secrets[k]
        secrets.pop(k, None)
        migrated = True
    merged = dict(secrets)
    merged.update(settings)
    if migrated:
        _write_yaml(BRIDGE_SECRETS_PATH, {k: v for k, v in merged.items() if k in SECRET_KEYS})
        _write_yaml(BRIDGE_SETTINGS_PATH, {k: v for k, v in merged.items() if k not in SECRET_KEYS})
    return merged


def _write_split(cfg):
    """把配置按「密钥 / 非密钥」分写到两个文件。"""
    secrets = {k: cfg.get(k, "") for k in SECRET_KEYS}
    settings = {k: v for k, v in cfg.items() if k not in SECRET_KEYS}
    ok1 = _write_yaml(BRIDGE_SECRETS_PATH, secrets)
    ok2 = _write_yaml(BRIDGE_SETTINGS_PATH, settings)
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
        for k in ("enabled", "app_id", "app_secret", "intents", "md_selector"):
            if k in raw:
                cfg[k] = raw[k]
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
        for k in ("enabled", "app_id", "app_secret", "intents", "md_selector"):
            if k in patch:
                cfg[k] = patch[k]
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
