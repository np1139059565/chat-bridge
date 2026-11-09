"""远程桥接 —— 包入口

对外提供 RemoteBridge 单例：统一管理 QQ 与微信两条通道的长连接、
事件分发与指令处理。

启动流程：
1. Flask 启动时调用 init_bridge()，按配置决定拉起哪些通道
2. 收到消息 → 对应 gateway 分发 → 卡片总线 / 指令处理
3. 抽屉上报消息 → 各通道各自的 router 分类去重 → 推送到对应平台

两条通道完全独立：
  QQ   —— WebSocket 长连接，AppID + AppSecret，逐条推送
  微信 —— HTTP 长轮询，扫码登录，合并推送（配额约束）
任一通道故障不影响另一条，也不影响服务其余功能。

设计原则：桥接层对网页 AI 完全透明。它不注册工具 provider、不进工具目录、
不写入 System Prompt。网页 AI 感知不到它的存在。
"""
from . import bridge_store, qq_gateway, command_panel
from . import weixin_gateway, weixin_login
from . import wecom_client, wecom_gateway
from .adapters.qq import QQAdapter
from .adapters.weixin import WeixinAdapter
from .adapters.wecom import WecomAdapter
import app_log


def log(*args):
    """统一前缀打印。"""
    app_log.info("[bridge]", *args)


class RemoteBridge:
    """桥接层总控：持有 QQ 与微信两条通道的客户端与事件网关。"""

    def __init__(self):
        # 各通道的指令回调都带上通道名：指令层据此查出该通道绑定的站点，
        # 把命令定向投给对应页面（QQ 跟 DeepSeek、企微跟 GLM 互不干扰）。
        def _on_command(channel_name):
            """生成一条「带通道名」的指令回调。

            包装而非改 handle_command 签名：调用点有三处网关 + 两处网页，
            改签名会波及全部；包装只动这里一处，签名保持不变（默认通道空）。
            @param channel_name 通道标识（qq / wecom / weixin）
            @returns {Function} 符合网关预期的 on_command 回调
            """
            def handler(qq_client, openid, msg_id, text):
                return command_panel.handle_command(
                    qq_client, openid, msg_id, text, channel=channel_name)
            return handler
        # QQ 通道
        self.client = None
        self.gateway = qq_gateway.QqGateway(on_command=_on_command("qq"))
        # 微信通道
        self.wx_client = None
        self.wx_gateway = weixin_gateway.WeixinGateway(on_command=_on_command("weixin"))
        self.wx_login = None
        # 企业微信通道（第三条）：WebSocket 长连接，支持主动推送与图片/文件
        self.wecom_client = None
        self.wecom_gateway = wecom_gateway.WecomGateway(on_command=_on_command("wecom"))
        # 统一推送管线的通道适配器：client 在各通道启动后再注入，
        # 构造期不持有客户端，避免启动顺序耦合。
        self.qq_adapter = QQAdapter()
        self.weixin_adapter = WeixinAdapter()
        self.wecom_adapter = WecomAdapter()

    # ---------- QQ ----------
    def _check_startable(self, cfg):
        """QQ 启动前置检查：开关打开、凭证齐全、依赖已装。

        返回 (app_id, app_secret)；任一条件不满足返回 (None, None)。
        """
        if not cfg.get("enabled"):
            log("QQ 桥接未启用，跳过启动")
            return None, None
        app_id = cfg.get("app_id") or ""
        app_secret = cfg.get("app_secret") or ""
        if not app_id or not app_secret:
            log("缺少 QQ AppID / AppSecret，无法启动")
            return None, None
        from .qq_client import HAS_WS
        if not HAS_WS:
            log("未安装 websocket-client，QQ 通道无法启动")
            return None, None
        return app_id, app_secret

    def _try_register_panel(self):
        """启动后尝试注册指令面板；失败不影响消息收发，故只记录。"""
        try:
            command_panel.register_panel(self.client)
        except Exception as e:
            log("注册指令面板失败：", e)

    def _start_qq(self, cfg):
        """按配置启动 QQ 通道。

        @param cfg 桥接配置
        @returns 是否成功启动
        """
        app_id, app_secret = self._check_startable(cfg)
        if not app_id:
            return False
        from .qq_client import QQClient
        intents = cfg.get("intents") or None
        self.client = QQClient(app_id, app_secret, self.gateway.handle_event, intents=intents)
        self.gateway.qq_client = self.client
        ok = self.client.start()
        if ok:
            self._try_register_panel()
        return ok

    def _stop_qq(self):
        """停止 QQ 通道。"""
        if self.client:
            self.client.stop()
            self.client = None

    # ---------- 微信 ----------
    def _start_weixin(self, cfg):
        """按配置启动微信通道。

        与 QQ 的差别：微信没有 AppID/AppSecret，凭证来自扫码登录。
        因此这里的「能否启动」只看开关与本地凭证是否存在；
        没有凭证就只是不跑长轮询，页面仍可发起扫码。
        @param cfg 桥接配置
        @returns 是否成功启动
        """
        wx = cfg.get("weixin") or {}
        if not wx.get("enabled"):
            log("微信通道未启用，跳过启动")
            return False
        import paths
        from .weixin_client import WeixinClient
        # ctx_path 必须传：上下文令牌随每条入向消息下发，发送时要原样回传；
        # 只存内存的话重启即失联，每次发送都会被服务端以参数错误拒绝。
        self.wx_client = WeixinClient(
            paths.WEIXIN_CRED_PATH, paths.WEIXIN_BUF_PATH, self.wx_gateway.handle_message,
            ctx_path=paths.WEIXIN_CTX_PATH)
        self.wx_gateway.client = self.wx_client
        # 登录管理器与客户端绑定：扫码成功后凭证直接写进客户端
        self.wx_login = weixin_login.WeixinLogin(self.wx_client)
        if not self.wx_client.has_cred() and not self.wx_client.load_cred():
            log("微信尚无登录凭证，等待页面发起扫码")
            return False
        ok = self.wx_client.start()
        if ok:
            log("微信通道已启动")
        return ok

    def _stop_weixin(self):
        """停止微信通道。"""
        if self.wx_client:
            self.wx_client.stop()
        self.wx_client = None

    def ensure_wx_login(self):
        """确保登录管理器可用（页面扫码前调用）。

        微信通道未启用时也需要它，故按需惰性创建。
        @returns WeixinLogin 实例
        """
        if self.wx_login:
            return self.wx_login
        import paths
        from .weixin_client import WeixinClient
        if not self.wx_client:
            self.wx_client = WeixinClient(
                paths.WEIXIN_CRED_PATH, paths.WEIXIN_BUF_PATH, self.wx_gateway.handle_message,
                ctx_path=paths.WEIXIN_CTX_PATH)
            self.wx_gateway.client = self.wx_client
        self.wx_login = weixin_login.WeixinLogin(self.wx_client)
        return self.wx_login

    # ---------- 企业微信 ----------
    def _start_wecom(self, cfg):
        """按配置启动企业微信通道。

        与微信的差别：微信凭证来自扫码，企业微信凭证是手工填的 BotID/Secret。
        两者都只看开关与凭证是否齐备；缺凭证就不启动，页面仍可保存配置。
        @param cfg 桥接配置
        @returns 是否成功启动
        """
        wc = cfg.get("wecom") or {}
        if not wc.get("enabled"):
            log("企业微信通道未启用，跳过启动")
            return False
        bot_id = (wc.get("bot_id") or "").strip()
        secret = (wc.get("secret") or "").strip()
        if not bot_id or not secret:
            log("缺少企业微信 BotID / Secret，无法启动")
            return False
        self.wecom_client = wecom_client.WecomClient(
            bot_id, secret, self.wecom_gateway.handle_message)
        self.wecom_gateway.client = self.wecom_client
        ok = self.wecom_client.start()
        if ok:
            log("企业微信通道已启动")
        return ok

    def _stop_wecom(self):
        """停止企业微信通道。"""
        if self.wecom_client:
            self.wecom_client.stop()
        self.wecom_client = None

    # ---------- 生命周期 ----------
    def start(self):
        """按配置启动全部通道。已启动则先停再起（配置可能变了）。"""
        cfg = bridge_store.get_config()
        self.stop()
        qq_ok = self._start_qq(cfg)
        wx_ok = self._start_weixin(cfg)
        wc_ok = self._start_wecom(cfg)
        return qq_ok or wx_ok or wc_ok

    def stop(self):
        """停止全部通道。"""
        self._stop_qq()
        self._stop_weixin()
        self._stop_wecom()

    def restart(self):
        """重启全部通道：配置变更后调用。"""
        self.stop()
        return self.start()

    def report(self, payload):
        """处理抽屉上报：只推给「最近活跃渠道」。

        为什么要独占：多通道同时启用时，同一条 AI 回复会被广播到每一条，
        用户在 QQ 里问一句，企业微信也收到一份，像是机器人在到处复读。
        正确行为是「谁最后跟我说话，回复就回给谁」。

        活跃渠道由 active_channel 登记，各网关收到用户消息时写入
        （QQ / 网页 / 企业微信三处）。取不到记录时（服务刚启动、
        尚无任何入向消息）退回广播，避免所有渠道都静默。

        @param payload 上报体
        @returns 推送条数（保持既有接口语义，返回 QQ 通道条数）
        """
        cfg = bridge_store.get_config()
        # 取活跃渠道；空串表示尚无记录，此时维持广播
        import active_channel
        target = active_channel.get()
        # 统一推送管线是唯一出口：旧的三套 router 已移除，
        # 不再保留 use_pipeline 回退开关。
        return self._report_via_pipeline(cfg, payload, target)

    def _report_via_pipeline(self, cfg, payload, target):
        """走统一推送管线：三条通道共用一套去重、配额与组装流程。

        @param cfg     桥接配置
        @param payload 上报体
        @param target  活跃渠道名；空串表示尚无记录
        @returns 推送条数
        """
        from .channel import push_pipeline
        import channel_binding
        push = cfg.get("push") or {}
        # 广播开关：打开后所有已启用的通道各收一份，避免单条通道丢消息导致漏看
        broadcast = bool(cfg.get("broadcast"))
        sent = 0
        # 按通道绑定过滤：某通道若绑定了站点，只推该站点的消息。
        # 这是「QQ 只跟 DeepSeek、企微只跟 GLM」的推送侧落实——
        # 未绑定站点的通道照旧接收全部消息（保持旧行为）。
        site = str(payload.get("siteKey") or "")
        # 三条通道按同一套规则调度，差异全在各自的适配器里
        if cfg.get("enabled") and self.client and self._wants(target, "qq", broadcast) \
                and self._site_ok("qq", site):
            try:
                self.qq_adapter.client = self.client
                sent = push_pipeline.run(self.qq_adapter, payload, push, log)
            except Exception as e:
                log("QQ 推送异常（管线）：", e)
        wx = cfg.get("weixin") or {}
        if wx.get("enabled") and self.wx_client and self._wants(target, "weixin", broadcast) \
                and self._site_ok("weixin", site):
            try:
                self.weixin_adapter.client = self.wx_client
                push_pipeline.run(self.weixin_adapter, payload, push, log)
            except Exception as e:
                log("微信推送异常（管线）：", e)
        wc = cfg.get("wecom") or {}
        if wc.get("enabled") and self.wecom_client and self._wants(target, "wecom", broadcast) \
                and self._site_ok("wecom", site):
            try:
                self.wecom_adapter.client = self.wecom_client
                push_pipeline.run(self.wecom_adapter, payload, push, log)
            except Exception as e:
                log("企业微信推送异常（管线）：", e)
        return sent

    @staticmethod
    def _site_ok(channel, site):
        """判断某通道本轮是否该接收这个站点的消息。

        三条通道都是单窗口，同时开多个网页 AI 时若不按站点过滤，
        各站回复会混进同一个聊天窗口。绑定后各看各的：
        - 通道未绑定站点 → 全部接收（旧行为，不改变现有用法）；
        - 通道已绑定 → 只接收该站点的消息；
        - 消息未带站点（历史数据）→ 绑定通道也接收，避免丢历史。

        @param channel 通道名（qq / wecom / weixin）
        @param site    本条消息所属站点；空串表示来源未知
        @returns {boolean} 是否推送
        """
        import channel_binding
        bound = channel_binding.get(channel)
        if not bound:
            return True
        if not site:
            return True
        return bound == site

    @staticmethod
    def _wants(target, channel, broadcast=False):
        """判断某个通道本轮是否该推送。

        两种模式：
          broadcast=True  广播 —— 所有已启用且在线的通道都推一份
          broadcast=False 单通道 —— 只推给最近说话的通道

        广播模式的用途：某条通道不稳时，另一条能兜住同一份内容，
        用户不至于因为一条通道丢消息而漏看。代价是同一条回复会出现两次，
        且各通道各自记账（去重集合按通道隔离），互不干扰。

        @param target    活跃渠道名；空串表示尚无记录
        @param channel   本方法要判断的通道名
        @param broadcast 是否广播模式
        @returns 该推返回 True
        """
        # 广播：不限来源，谁在线就推给谁
        if broadcast:
            return True
        if not target:
            return True
        # 微信通道未在 active_channel 中登记，仅在活跃渠道不是 QQ 时参与
        if channel == "weixin":
            return target != "qq"
        return target == channel

    def status(self):
        """返回桥接状态，供设置页展示与排查。

        connected 取客户端的 _ws_connected（真正连上才为真），
        而不是 _running（只表示尝试启动过）——否则指示灯会虚亮。
        """
        cfg = bridge_store.get_config()
        connected = bool(self.client and getattr(self.client, "_ws_connected", False))
        last_event = getattr(self.client, "_last_event", "") if self.client else ""
        wx_cfg = cfg.get("weixin") or {}
        wx_connected = bool(self.wx_client and getattr(self.wx_client, "_ws_connected", False))
        wc_cfg = cfg.get("wecom") or {}
        return {
            "enabled": bool(cfg.get("enabled")),
            "connected": connected,
            "appId": cfg.get("app_id") or "",
            "push": cfg.get("push") or {},
            "lastEvent": last_event,
            "intents": getattr(self.client, "intents", 0) if self.client else 0,
            # 微信通道状态
            "weixin": {
                "enabled": bool(wx_cfg.get("enabled")),
                "connected": wx_connected,
                "hasCred": bool(self.wx_client and self.wx_client.has_cred()),
                "botId": ((self.wx_client._cred or {}).get("bot_id") if self.wx_client else "") or "",
                "lastEvent": getattr(self.wx_client, "_last_event", "") if self.wx_client else "",
            },
            # 企业微信通道状态
            "wecom": {
                "enabled": bool(wc_cfg.get("enabled")),
                "connected": bool(self.wecom_client and getattr(self.wecom_client, "_connected", False)),
                "hasCred": bool((wc_cfg.get("bot_id") or "").strip()
                                and (wc_cfg.get("secret") or "").strip()),
                "botId": (wc_cfg.get("bot_id") or ""),
                "lastEvent": getattr(self.wecom_client, "_last_event", "") if self.wecom_client else "",
            },
        }


# 全局单例
bridge = RemoteBridge()


def init_bridge():
    """服务启动时的初始化入口：按配置拉起各通道。

    失败不阻断 Flask 启动——桥接是可选功能，
    凭证未填或依赖未装时，其余工具功能照常可用。
    """
    try:
        return bridge.start()
    except Exception as e:
        log("初始化异常（不阻断服务启动）：", e)
        return False
