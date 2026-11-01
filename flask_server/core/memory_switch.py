"""AI 工具调用镜像插件 —— 记忆系统总开关

职责：回答「当前是否允许碰记忆库」这一个问题。

背景：界面请求的响应优先级最高，任何后台维护都不允许堵住它。
记忆库是 SQLite 单写者，持有写锁期间其它请求会被 busy_timeout 拖住，
故提供此总开关：开关关闭时，记忆库连接、后台调度、上报写入、HTTP 接口
一律不执行，从操作层面杜绝「记忆写入拖慢界面」的可能。

开关来源：runtime.yaml 的 bridge.push.check_memory（与设置页同字段）。
未配置时视为「开启」，保持与既有默认行为一致。

依赖：config_file、threading、time
"""
import threading
import time

import config_file

# 配置缓存：避免每次判断都解析 YAML。
# 取值权衡：缓存 2 秒，配置改动最多延迟 2 秒生效，
# 对「手动切换开关」这一低频操作完全够用，又能挡住高频轮询的重复解析。
_CACHE_TTL = 2.0
_cache_value = None      # 缓存值：True/False；None 表示尚未读取
_cache_at = 0.0          # 缓存时间戳（秒）
_cache_lock = threading.Lock()

# 测试覆盖值：None 表示不覆盖（按配置走）；True/False 表示强制指定。
# 存在的意义：自测不应依赖本机真实配置——用户可能恰好关着这个开关，
# 那样所有记忆测试都会因「功能被关」而失败，测不到真实逻辑。
_override = None


def _read_from_config():
    """从配置中读取记忆开关；读取失败时保守返回 True（保持既有行为）。

    @returns 是否允许记忆系统运行
    """
    try:
        # check_memory 存在 bridge 分区的 push 子字典里（设置页同一字段）
        bridge = config_file.get_runtime_section("bridge") or {}
        push = bridge.get("push") or {}
        v = push.get("check_memory")
        # 未配置：沿用默认「开启」，避免旧配置文件升级后功能突然消失
        if v is None:
            return True
        return bool(v)
    except Exception:
        # 配置不可读时不阻断：宁可让记忆照常工作，也不能因读配置失败把它整体关掉
        return True


def is_enabled():
    """记忆系统是否启用（带短时缓存）。

    @returns True 表示允许读写记忆库；False 表示一律禁止
    """
    global _cache_value, _cache_at
    # 测试覆盖优先：自测可强制指定开关状态，不依赖本机真实配置
    if _override is not None:
        return _override
    now = time.time()
    # 缓存命中：直接返回，避免高频调用反复解析配置
    if _cache_value is not None and (now - _cache_at) < _CACHE_TTL:
        return _cache_value
    with _cache_lock:
        # 双重检查：等锁期间可能已被其它线程刷新
        now = time.time()
        if _cache_value is not None and (now - _cache_at) < _CACHE_TTL:
            return _cache_value
        _cache_value = _read_from_config()
        _cache_at = now
        return _cache_value


def invalidate():
    """立即让缓存失效，使下一次 is_enabled 重新读配置。

    供「保存设置」接口调用，让开关切换立刻生效，无需等缓存过期。
    """
    global _cache_value, _cache_at
    with _cache_lock:
        _cache_value = None
        _cache_at = 0.0


def set_override(value):
    """测试专用：强制指定开关状态，绕过配置读取。

    @param value True/False 强制开启或关闭；None 取消覆盖、恢复按配置判断
    """
    global _override
    _override = None if value is None else bool(value)


def clear_override():
    """测试专用：取消强制覆盖，恢复按配置判断。"""
    set_override(None)
