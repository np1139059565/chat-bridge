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


def _normalize_url(url):
    """把页面地址归一成可比较的形式。

    绑定表里存的是用户选择页面时的完整地址，推送时带上来的地址可能多一个
    末尾斜杠、带查询参数、大小写不同。直接用字符串相等比，任何一点差异都会
    让「绑定过的页面」被误判成不匹配，整条通道被过滤成空——这是「绑定也没用」
    的直接成因之一。

    归一规则：小写 scheme 与 host，去掉末尾斜杠，丢弃 fragment，保留路径与
    查询串（不同会话可能只差查询参数）。

    @param url 原始地址
    @returns {string} 归一后的地址；无法解析时返回去空白的原文
    """
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        from urllib.parse import urlsplit, urlunsplit
        parts = urlsplit(raw)
        scheme = (parts.scheme or "").lower()
        netloc = (parts.netloc or "").lower()
        path = parts.path or ""
        # 末尾斜杠对同一页面没有语义差异，统一去掉；根路径保留单个斜杠
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
        # fragment 不参与页面身份判定
        return urlunsplit((scheme, netloc, path, parts.query, ""))
    except Exception:
        return raw.rstrip("/")


def matches(channel, page_url):
    """判断某个页面发来的消息是否该推给该通道。

    规则（宁可漏推，不串台）：
    - 通道未绑定 → 全部接收（旧行为，绑定前不做限制）；
    - 通道已绑定 → 只接收该页面的消息；
    - 消息未带页面 → 已绑定的通道一律拒绝。页面未知时无法确认归属，
      放行就等于让任意页面的内容流进这条通道，与「不许串台」相反。

    @param channel  通道名
    @param page_url 消息来源页面
    @returns {boolean} 是否推送
    """
    bound = get(channel)                                    # 取该通道绑定的页面地址
    if not bound:                                           # 未绑定：不设限，全部放行
        return True
    src = str(page_url or "").strip()                       # 本次上报携带的来源页面地址
    # 页面未知：已绑定通道拒绝，避免来源不明的内容串进来
    if not src:
        _diag("拒收", channel, bound, src, "上报未携带 page_url")   # 记录拒收原因，便于定位
        return False
    # 归一化后比较：消除末尾斜杠、大小写、fragment 等无意义差异
    nb = _normalize_url(bound)                              # 绑定侧归一化结果
    ns = _normalize_url(src)                                # 上报侧归一化结果
    if nb != ns:                                            # 归一化后仍不等：地址漂移
        _diag("拒收", channel, bound, src, "归一化后不相等 bound=%s src=%s" % (nb, ns))
        return False
    _diag("放行", channel, bound, src, "匹配成功")             # 命中：记录一次成功匹配
    return True


def _diag(action, channel, bound, src, detail):
    """输出页面过滤诊断日志，供排查「绑定后收不到消息」。

    只做观测，不改变任何判定结果；日志失败也绝不影响过滤主流程。

    @param action  结果动作（放行 / 拒收）
    @param channel 通道名
    @param bound   绑定表里的页面地址
    @param src     上报携带的页面地址
    @param detail  补充说明
    """
    try:
        import app_log
        app_log.warn("[channel_binding]", action, "通道=%s" % channel,
                     "bound=%r" % bound, "src=%r" % src, detail)
    except Exception:
        try:
            import sys
            sys.stderr.write("[channel_binding] %s 通道=%s bound=%r src=%r %s\n"
                             % (action, channel, bound, src, detail))
        except Exception:
            pass
