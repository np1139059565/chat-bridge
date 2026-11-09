"""远程桥接 —— 多页面接管指令（/pages、/page）

一台电脑同时开多个网页 AI 时，需要指定指令投给哪个页面，否则会串台。
本模块只做「列出页面」与「切换接管页面」两件事，页面状态本身由
core/page_registry.py 维护。

从 command_panel.py 抽出（2026-11-09：该文件因新增指令达到 496 行、
超出仓库 450 行上限）。依赖单向：command_panel 引用本模块。
"""

from .command_dispatch import _reply


def handle_pages(qq_client, openid, arg, msg_id):
    """列出当前在线的网页 AI 页面，并标出正在接管的那一个。

    多网页 AI 并存时，用户需要知道「现在有哪些页面」「指令会投给谁」。
    序号与 /page N 的取值一一对应，可直接照抄。
    """
    import page_registry
    pages = page_registry.online()
    active = page_registry.get_active()
    if not pages:
        _reply(qq_client, openid, "当前没有在线的网页 AI 页面。\n"
               "请先打开网页并点开抽屉，等几秒后重试。")
        return
    lines = ["【在线页面 %d 个】" % len(pages)]
    for i, url in enumerate(pages, 1):
        mark = " ← 当前接管" if url == active else ""
        lines.append("%d. %s%s" % (i, url, mark))
    lines.append("")
    if not active:
        lines.append("未接管：指令会发给所有页面（可能串台）。")
        lines.append("用 /page 序号 指定接管页面。")
    else:
        lines.append("用 /page 序号 切换，/page off 取消接管。")
    _reply(qq_client, openid, "\n".join(lines))


def handle_page(qq_client, openid, arg, msg_id):
    """切换接管的页面：/page 1 按序号，/page off 取消接管。

    接管后指令只投给该页面的抽屉，其他页面取不到——这是多网页 AI
    并存时指令不串台的关键。未接管时指令仍广播给所有页面（旧行为）。
    """
    import page_registry
    sel = str(arg or "").strip()
    if not sel:
        # 不带参数等同 /pages，省一次输入
        return handle_pages(qq_client, openid, "", msg_id)
    url, err = page_registry.resolve(sel)
    if err:
        _reply(qq_client, openid, "切换失败：" + err + "\n用 /pages 查看在线页面。")
        return
    if not url:
        # off：取消接管
        page_registry.set_active("")
        _reply(qq_client, openid, "已取消接管：指令将发给所有页面。")
        return
    if not page_registry.set_active(url):
        _reply(qq_client, openid, "切换失败：该页面已离线。\n用 /pages 查看在线页面。")
        return
    _reply(qq_client, openid, "已接管：\n" + url + "\n此后指令只发给这个页面。")
