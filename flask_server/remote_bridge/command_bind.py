"""远程桥接 —— 通道绑定指令（/bind）

用途：把某条通道固定绑到某个网页 AI 站点，实现「QQ 只跟 DeepSeek、
企微只跟 GLM」这类分工，两者互不干扰。

三条通道（qq / wecom / weixin）都是单窗口，同时开多个网页 AI 时若不绑定，
各站回复会混进同一个聊天窗口；绑定后各看各的。

用法：
    /bind            查看当前绑定
    /bind deepseek   把「当前这条通道」绑到 deepseek
    /bind off        解除当前通道的绑定

从 command_panel.py 抽出（该文件已在行数上限附近）。依赖单向：
command_panel 引用本模块。
"""

from .command_dispatch import _reply, current_channel


def _known_sites():
    """取已配置的站点 id 列表（排序）。取不到时返回空列表。

    @returns {list} 站点 id 列表
    """
    try:
        import runtime
        profiles = (runtime.CONFIG or {}).get("profiles") or {}
        return sorted(profiles.keys())
    except Exception:
        return []


def _show_binding(qq_client, openid, channel):
    """回复当前绑定状态与可选站点。

    @param channel 通道名
    """
    import channel_binding
    bound = channel_binding.get(channel) or "（未绑定，接收全部站点）"
    lines = ["当前通道：" + channel, "绑定站点：" + bound, ""]
    ids = _known_sites()
    if ids:
        lines.append("可选站点：" + " / ".join(ids))
    lines.append("用法：/bind 站点名  或  /bind off")
    _reply(qq_client, openid, "\n".join(lines))


def handle_bind(qq_client, openid, arg, msg_id):
    """绑定或查看当前通道的站点绑定。

    绑定的作用范围是「当前这条通道」：在 QQ 里敲就绑 QQ，在企微里敲就绑企微，
    互不影响。这正是用户要的「QQ 跟 DeepSeek、企微跟 GLM」。
    """
    import channel_binding
    channel = current_channel()
    if not channel:
        _reply(qq_client, openid, "无法确定当前通道，绑定指令只在 QQ / 企微 / 微信里可用")
        return
    sel = str(arg or "").strip().lower()
    # 不带参数：查看当前绑定与可选站点
    if not sel:
        _show_binding(qq_client, openid, channel)
        return
    # off：解除绑定
    if sel == "off":
        channel_binding.bind(channel, "")
        _save_bindings()
        _reply(qq_client, openid, "已解除绑定：%s 通道将接收全部站点的消息" % channel)
        return
    _bind_site(qq_client, openid, channel, sel)


def _bind_site(qq_client, openid, channel, site):
    """把通道绑到指定站点（先校验站点存在）。

    @param channel 通道名
    @param site    站点 id
    """
    import channel_binding
    ids = _known_sites()
    if ids and site not in ids:
        _reply(qq_client, openid, "没有站点「%s」。可选：%s" % (site, " / ".join(ids)))
        return
    channel_binding.bind(channel, site)
    _save_bindings()
    _reply(qq_client, openid,
           "已绑定：%s 通道 ↔ %s\n此后这条通道只收发该站点的消息。" % (channel, site))


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
            app_log.warn("[bridge][bind]", "保存绑定失败（内存已生效）：", e)
        except Exception:
            pass
