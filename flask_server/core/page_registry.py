"""页面登记表 —— 多网页 AI 并存时的页面归属与接管状态

解决的问题：一台电脑同时开多个网页 AI（千问 / 元宝 / Kimi …）时，
每张指令卡片都没有「目标页面」概念，取件接口返回全部未确认卡片，
于是任何页面的抽屉都可能取走别人的指令，表现为指令串台。

本模块维护两样东西：
1. 在线页面表：抽屉轮询时登记自己的页面地址与最后活跃时间；
2. 当前接管页面：指令默认投给哪个页面。为空表示未接管（向后兼容，
   维持旧的广播行为：谁先取到算谁的）。

设计取向：
- 内存态、不落盘。页面在线与否本就随标签页开关变化，重启后重新登记即可；
- 只做归属判断，不碰卡片投递细节（那是 card_bus 的职责）。
"""
import threading
import time

# 页面超过这么久没轮询即视为已关闭（抽屉轮询间隔约 5 秒，留足余量）
PAGE_TTL_SEC = 90

_lock = threading.Lock()
# {page_url: 最后活跃时间戳}
_pages = {}
# 当前接管页面；空串 = 未接管，指令广播给所有页面
_active = ""


def touch(page_url):
    """登记一次页面活跃（每次轮询调用）。

    @param page_url 页面地址；空值直接忽略，避免脏数据进表
    """
    url = str(page_url or "").strip()
    if not url:
        return
    with _lock:
        _pages[url] = time.time()


def online():
    """取当前在线页面列表（按地址排序，剔除超时项）。

    @returns {list} 页面地址列表
    """
    now = time.time()
    out = []
    with _lock:
        # 顺手清理超时项：页面关闭后不该一直占着列表
        for url in [u for u, t in _pages.items() if now - t > PAGE_TTL_SEC]:
            _pages.pop(url, None)
        out = sorted(_pages.keys())
    return out


def get_active():
    """取当前接管页面；空串表示未接管（指令广播）。"""
    with _lock:
        return _active


def set_active(page_url):
    """设置接管页面。

    @param page_url 页面地址；传空串表示取消接管、恢复广播
    @returns {boolean} 是否设置成功（非空时要求该页面在线）
    """
    global _active
    url = str(page_url or "").strip()
    with _lock:
        if url and url not in _pages:
            return False
        _active = url
        return True


def resolve(selector):
    """把用户输入的页面选择器解析为页面地址。

    支持三种写法，都是为了让手机上打字尽量短：
    - 序号（1 起）：对应 online() 的第 N 项
    - off：取消接管
    - 完整/部分地址：按子串匹配，唯一命中才算成功

    @param selector 用户输入
    @returns {tuple} (页面地址, 错误说明)；成功时错误说明为空串
    """
    sel = str(selector or "").strip()
    if not sel:
        return "", "请给出页面序号或地址"
    if sel.lower() == "off":
        return "", ""
    pages = online()
    if sel.isdigit():
        return _by_index(sel, pages)
    return _by_fragment(sel, pages)


def _by_index(sel, pages):
    """按序号取页面（1 起）。

    @param sel   纯数字字符串
    @param pages 在线页面列表
    @returns {tuple} (页面地址, 错误说明)
    """
    idx = int(sel)
    if idx < 1 or idx > len(pages):
        return "", "序号超出范围（当前 %d 个页面）" % len(pages)
    return pages[idx - 1], ""


def _by_fragment(sel, pages):
    """按地址子串匹配页面。有歧义时报错，绝不猜一个。

    @param sel   用户输入的地址片段
    @param pages 在线页面列表
    @returns {tuple} (页面地址, 错误说明)
    """
    hits = [u for u in pages if sel in u]
    if len(hits) == 1:
        return hits[0], ""
    if not hits:
        return "", "没有页面匹配「%s」" % sel
    return "", "「%s」匹配到 %d 个页面，请给更精确的片段" % (sel, len(hits))


def reset():
    """清空登记（测试与热重载用）。"""
    global _active
    with _lock:
        _pages.clear()
        _active = ""
