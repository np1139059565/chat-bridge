"""通道与页面的绑定表 —— 每条单窗口通道各看各的网页 AI

解决的问题：QQ 与企微都是单窗口，同时开多个网页 AI 时，两者的消息会混在
同一片页面池里，无法做到「QQ 只跟 DeepSeek 页面、企微只跟 GLM 页面」。

设计取向（用户拍板）：只保留一套指令，绑定的是**页面**而非站点。
用户每次只关注某一个页面，直接在页面列表里选一个即可，不必先想站点再找页面。

与 page_registry 的分工：
- page_registry 记录「哪些页面在线」；
- 本模块记录「哪条通道固定看哪个页面」（按通道、持久化、互不干扰）。

持久化：绑定关系写进运行时配置，重启后保持。
"""
import threading

# 绑定表：{通道名: 页面地址}。通道名为适配器的 name（qq / wecom / weixin）。
# 未绑定的通道不做过滤，保持旧行为（所有页面消息都推给它）。
_bindings = {}
_lock = threading.Lock()


def get(channel):
    """取某条通道绑定的页面地址；未绑定时返回空串。

    @param channel 通道名（qq / wecom / weixin）
    @returns {string} 页面地址；未绑定为空串
    """
    with _lock:
        return str(_bindings.get(str(channel or "")) or "")


def bind(channel, page_url):
    """绑定通道到页面。

    @param channel  通道名
    @param page_url 页面地址；传空串表示解除绑定
    @returns {boolean} 是否发生了改变
    """
    ch = str(channel or "").strip()
    if not ch:
        return False
    page = str(page_url or "").strip()
    with _lock:
        old = _bindings.get(ch, "")
        if page:
            _bindings[ch] = page
        else:
            _bindings.pop(ch, None)
        return old != page


def all_bindings():
    """取全部绑定（副本）。

    @returns {dict} {通道名: 页面地址}
    """
    with _lock:
        return dict(_bindings)


def load_from_config(cfg):
    """从配置字典载入绑定表（启动时调用）。

    @param cfg 形如 {"qq": "https://chat.deepseek.com/..."} 的字典
    """
    with _lock:
        _bindings.clear()
        if isinstance(cfg, dict):
            for ch, page in cfg.items():
                ch = str(ch or "").strip()
                page = str(page or "").strip()
                if ch and page:
                    _bindings[ch] = page


def reset():
    """清空绑定（测试用）。"""
    with _lock:
        _bindings.clear()


def matches(channel, page_url):
    """判断某个页面发来的消息是否该推给该通道。

    规则（宁多推不漏推）：
    - 通道未绑定 → 全部接收（旧行为）；
    - 通道已绑定 → 只接收该页面的消息；
    - 消息未带页面（历史数据）→ 绑定通道也接收，避免丢历史。

    @param channel  通道名
    @param page_url 消息来源页面
    @returns {boolean} 是否推送
    """
    bound = get(channel)
    if not bound:
        return True
    src = str(page_url or "").strip()
    if not src:
        return True
    return bound == src
