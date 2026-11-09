"""通道与站点的绑定表 —— 每条通道各看各的网页 AI

解决的问题：QQ 与企微都是单窗口，但同时开多个网页 AI 时，
两者的消息会混在同一片页面池里，无法做到「QQ 只跟 DeepSeek 对话、
企微只跟 GLM 对话」。

本模块维护「通道 → 站点」的绑定：
- 收消息时按来源通道查出绑定站点，据此把消息定向投给该站点的页面；
- 推消息时按通道绑定过滤，只推属于本站点的回复。

与 page_registry 的分工：
- page_registry 管「当前接管哪个页面」（全局、手动切换、影响网页端）；
- 本模块管「哪条通道固定跟哪个站点」（按通道、持久化、互不干扰）。

持久化：绑定关系写进运行时配置（本机偏好、不入库），重启后保持。
"""
import threading

# 绑定表：{通道名: 站点 id}。通道名为适配器的 name（qq / wecom / weixin）。
# 未绑定的通道不做过滤，保持旧行为（所有站点消息都推给它）。
_bindings = {}
_lock = threading.Lock()


def get(channel):
    """取某条通道绑定的站点 id；未绑定时返回空串。

    @param channel 通道名（qq / wecom / weixin）
    @returns {string} 站点 id；未绑定为空串
    """
    with _lock:
        return str(_bindings.get(str(channel or "")) or "")


def bind(channel, site_key):
    """绑定通道到站点。

    @param channel  通道名
    @param site_key 站点 id；传空串表示解除绑定
    @returns {boolean} 是否发生了改变
    """
    ch = str(channel or "").strip()
    if not ch:
        return False
    site = str(site_key or "").strip()
    with _lock:
        old = _bindings.get(ch, "")
        if site:
            _bindings[ch] = site
        else:
            _bindings.pop(ch, None)
        return old != site


def all_bindings():
    """取全部绑定（副本）。

    @returns {dict} {通道名: 站点 id}
    """
    with _lock:
        return dict(_bindings)


def load_from_config(cfg):
    """从配置字典载入绑定表（启动时调用）。

    @param cfg 形如 {"qq": "deepseek", "wecom": "glm"} 的字典
    """
    with _lock:
        _bindings.clear()
        if isinstance(cfg, dict):
            for ch, site in cfg.items():
                ch = str(ch or "").strip()
                site = str(site or "").strip()
                if ch and site:
                    _bindings[ch] = site


def reset():
    """清空绑定（测试用）。"""
    with _lock:
        _bindings.clear()


# 站点 id → 域名片段。键为档案 id，值为该站点页面地址里出现的特征串。
# 只登记「id 与域名主体不一致」的站点；其余直接用 id 本身匹配。
SITE_HOST_HINTS = {
    "glm": "chatglm", "wenxin": "wenxin", "deepseek": "deepseek",
    "qianwen": "qianwen", "yuanbao": "yuanbao",
    "xinghuo": "xinghuo", "kimi": "kimi",
}


def _pick_page(site, online, active):
    """在在线页面里挑一个属于该站点的（接管页优先）。

    @param site   站点 id
    @param online 在线页面列表
    @param active 当前接管页面；空串表示未接管
    @returns {string} 页面地址；该站点无在线页面时为空串
    """
    frag = SITE_HOST_HINTS.get(site, site)
    candidates = [u for u in online if frag in u]
    if not candidates:
        return ""
    if active and active in candidates:
        return active
    return candidates[0]


def resolve_target_page(channel):
    """把通道绑定解析为该站点当前在线的页面地址。

    解析顺序：该站点的接管页优先，否则取第一个在线页面；
    无在线页面则返回空串（退回广播，不卡住消息）。

    @param channel 通道名
    @returns {string} 页面地址；无法确定为空串
    """
    site = get(channel)
    if not site:
        return ""
    try:
        import page_registry
        return _pick_page(site, page_registry.online(), page_registry.get_active())
    except Exception:
        return ""
