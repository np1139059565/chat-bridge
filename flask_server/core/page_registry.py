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

_lock = threading.Lock()
# 在线页面集合。上下线一律由抽屉显式上报：打开即登记、关闭或卸载即注销。
# 不设超时剔除——页面切到后台被浏览器节流时仍然是打开着的页面，
# 按超时判离线会让它的消息改投到别的站点，那才是真正的串台来源。
_pages = set()
# 当前接管页面；空串 = 未接管，指令广播给所有页面
_active = ""


def register(page_url):
    """登记一个页面为在线（抽屉打开时上报）。

    打开抽屉即上线，不等待任何轮询或超时判定。

    @param page_url 页面地址；空值直接忽略，避免脏数据进表
    """
    url = str(page_url or "").strip()  # 规范化：去空白，空地址视为无效
    if not url:                         # 空地址不登记，防止脏数据污染集合
        return
    with _lock:                         # 加锁：Flask 多线程并发读写同一集合
        _pages.add(url)                 # 加入在线集合（重复加入无副作用）


def unregister(page_url):
    """注销一个页面（抽屉关闭或页面卸载时上报）。

    显式下线，不残留任何待清理状态。

    @param page_url 页面地址；空值直接忽略
    """
    url = str(page_url or "").strip()  # 规范化，与 register 保持同一口径
    if not url:                         # 空地址无从注销，直接返回
        return
    with _lock:                         # 加锁：与 register / online 互斥
        _pages.discard(url)             # discard：不存在也不报错


def online():
    """取当前在线页面列表（按地址排序）。

    只返回抽屉明确上报为在线的页面，不做任何超时推断。

    @returns {list} 页面地址列表
    """
    with _lock:                         # 加锁读取，避免与增删并发
        return sorted(_pages)           # 排序保证 /pages 序号稳定可复现


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
    with _lock:                 # 加锁：清空与并发读写互斥
        _pages.clear()          # 清空在线集合
        _active = ""            # 同时取消接管页
