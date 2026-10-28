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
from . import bridge_store, message_router, qq_gateway, command_panel
from . import weixin_gateway, weixin_router, weixin_login
import app_log


def log(*args):
    """统一前缀打印。"""
    app_log.info("[bridge]", *args)


class RemoteBridge:
    """桥接层总控：持有 QQ 与微信两条通道的客户端与事件网关。"""

    def __init__(self):
        # QQ 通道
        self.client = None
        self.gateway = qq_gateway.QqGateway(on_command=command_panel.handle_command)
        # 微信通道
        self.wx_client = None
        self.wx_gateway = weixin_gateway.WeixinGateway(on_command=command_panel.handle_command)
        self.wx_login = None

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
        self.wx_client = WeixinClient(
            paths.WEIXIN_CRED_PATH, paths.WEIXIN_BUF_PATH, self.wx_gateway.handle_message)
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
                paths.WEIXIN_CRED_PATH, paths.WEIXIN_BUF_PATH, self.wx_gateway.handle_message)
            self.wx_gateway.client = self.wx_client
        self.wx_login = weixin_login.WeixinLogin(self.wx_client)
        return self.wx_login

    # ---------- 生命周期 ----------
    def start(self):
        """按配置启动全部通道。已启动则先停再起（配置可能变了）。"""
        cfg = bridge_store.get_config()
        self.stop()
        qq_ok = self._start_qq(cfg)
        wx_ok = self._start_weixin(cfg)
        return qq_ok or wx_ok

    def stop(self):
        """停止全部通道。"""
        self._stop_qq()
        self._stop_weixin()

    def restart(self):
        """重启全部通道：配置变更后调用。"""
        self.stop()
        return self.start()

    def report(self, payload):
        """处理抽屉上报：分别推给 QQ 与微信。

        两条通道各自去重、各自记账，互不干扰；
        某一条失败不影响另一条，也不影响请求本身。
        @param payload 上报体
        @returns QQ 通道推送的条数（保持既有接口语义）
        """
        cfg = bridge_store.get_config()
        sent = 0
        if cfg.get("enabled"):
            try:
                sent = message_router.handle_report(self.client, payload)
            except Exception as e:
                log("QQ 推送异常：", e)
        wx = cfg.get("weixin") or {}
        if wx.get("enabled") and self.wx_client:
            try:
                weixin_router.handle_report(self.wx_client, payload)
            except Exception as e:
                log("微信推送异常：", e)
        return sent

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
