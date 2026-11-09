"""远程桥接 —— 页面绑定指令（/page）

用途：把「当前这条通道」固定到某个网页页面，实现「QQ 只跟 DeepSeek 页面、
企微只跟 GLM 页面」这类分工，两者互不干扰。

三条通道（qq / wecom / weixin）都是单窗口。用户每次只关注某一个页面，
所以只需要一条指令：列出在线页面、选一个绑上。

用法：
    /page            列出在线页面与当前绑定
    /page 1          把「当前这条通道」绑到第 1 个页面
    /page deepseek   按地址片段绑（唯一命中才算）
    /page off        解除当前通道的绑定

设计说明：不再区分 /bind 与 /page——绑定对象就是页面本身。
原先「站点绑定」需要先想站点再找页面，多一层概念且容易与页面接管打架。
"""

from .command_dispatch import _reply, current_channel


def handle_page(qq_client, openid, arg, msg_id):
    """查看或切换当前通道绑定的页面。

    作用范围是「当前这条通道」：在 QQ 里敲就绑 QQ，在企微里敲就绑企微。
    """
    import channel_binding
    channel = current_channel()
    if not channel:
        _reply(qq_client, openid, "无法确定当前通道，页面绑定只在 QQ / 企微 / 微信里可用")
        return
    sel = str(arg or "").strip()
    if not sel:
        _show_pages(qq_client, openid, channel)
        return
    if sel.lower() == "off":
        channel_binding.bind(channel, "")
        _save_bindings()
        _reply(qq_client, openid, "已解除绑定：%s 通道将接收全部页面的消息" % channel)
        return
    _bind_page(qq_client, openid, channel, sel)


def _show_pages(qq_client, openid, channel):
    """回复在线页面列表与当前绑定。

    @param channel 通道名
    """
    import channel_binding
    import page_registry
    pages = page_registry.online()
    bound = channel_binding.get(channel)
    lines = ["当前通道：" + channel,
             "绑定页面：" + (bound or "（未绑定，接收全部页面）"), ""]
    if not pages:
        lines.append("当前没有在线页面。请先打开网页并点开抽屉。")
    else:
        lines.append("【在线页面 %d 个】" % len(pages))
        for i, url in enumerate(pages, 1):
            mark = " ← 当前绑定" if url == bound else ""
            lines.append("%d. %s%s" % (i, url, mark))
        lines.append("")
        lines.append("用 /page 序号 绑定，/page off 解除。")
    _reply(qq_client, openid, "\n".join(lines))


def _bind_page(qq_client, openid, channel, sel):
    """把通道绑到指定页面（先解析选择器）。

    @param channel 通道名
    @param sel     序号或地址片段
    """
    import channel_binding
    import page_registry
    url, err = page_registry.resolve(sel)
    if err:
        _reply(qq_client, openid, "绑定失败：" + err + "\n用 /page 查看在线页面。")
        return
    if not url:
        _reply(qq_client, openid, "绑定失败：页面已离线。\n用 /page 查看在线页面。")
        return
    channel_binding.bind(channel, url)
    _save_bindings()
    _reply(qq_client, openid,
           "已绑定：%s 通道 →\n%s\n此后这条通道只收发该页面的消息。" % (channel, url))


def _save_bindings():
    """把绑定表写进运行时配置（本机偏好，不入库），重启后保持。

    写失败不影响当前进程内的绑定（内存已生效），只记日志。
    """
    try:
        import channel_binding
        import config_file
        cfg = config_file.get_runtime_section("app") or {}
        cfg["channel_bindings"] = channel_binding.all_bindings()
        config_file.update_runtime_section("app", cfg)
    except Exception as e:
        try:
            import app_log
            app_log.warn("[bridge][page]", "保存绑定失败（内存已生效）：", e)
        except Exception:
            pass
