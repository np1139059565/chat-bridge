"""远程桥接 —— 包入口

对外提供 RemoteBridge 单例：统一管理 QQ 长连接、事件分发与指令处理。

启动流程：
1. Flask 启动时调用 init_bridge()，按配置决定是否拉起 QQ 长连接
2. 收到 QQ 消息 → qq_gateway 分发 → 卡片总线 / 指令处理
3. 抽屉上报消息 → message_router 分类去重 → 被动回复推送到 QQ

设计原则：桥接层对网页 AI 完全透明。它不注册工具 provider、不进工具目录、
不写入 System Prompt。网页 AI 感知不到它的存在。
"""
from . import bridge_store, message_router, qq_gateway, command_panel


def log(*args):
    """统一前缀打印。"""
    print("[bridge]", *args)


class RemoteBridge:
    """桥接层总控：持有 QQ 客户端与事件网关。"""

    def __init__(self):
        self.client = None
        self.gateway = qq_gateway.QqGateway(on_command=command_panel.handle_command)

    def _check_startable(self, cfg):
        """启动前置检查：开关打开、凭证齐全、依赖已装。

        返回 (app_id, app_secret)；任一条件不满足返回 (None, None)。
        分成独立函数是为了让 start 只表达「怎么起」，不掺杂「能不能起」的分支。
        """
        if not cfg.get("enabled"):
            log("桥接未启用，跳过启动")
            return None, None
        app_id = cfg.get("app_id") or ""
        app_secret = cfg.get("app_secret") or ""
        if not app_id or not app_secret:
            log("缺少 AppID / AppSecret，无法启动")
            return None, None
        from .qq_client import HAS_WS
        if not HAS_WS:
            log("未安装 websocket-client，无法启动。请 pip install websocket-client")
            return None, None
        return app_id, app_secret

    def _try_register_panel(self):
        """启动后尝试注册指令面板；失败不影响消息收发，故只记录。"""
        try:
            command_panel.register_panel(self.client)
        except Exception as e:
            log("注册指令面板失败：", e)

    def start(self):
        """按配置启动桥接。已启动则先停再起（配置可能变了）。"""
        cfg = bridge_store.get_config()
        app_id, app_secret = self._check_startable(cfg)
        if not app_id:
            return False
        from .qq_client import QQClient
        self.stop()
        # intents：配置里为正数则用它，否则让客户端用默认值（单聊消息）
        intents = cfg.get("intents") or None
        self.client = QQClient(app_id, app_secret, self.gateway.handle_event, intents=intents)
        self.gateway.qq_client = self.client
        ok = self.client.start()
        if ok:
            self._try_register_panel()
        return ok

    def stop(self):
        """停止桥接。"""
        if self.client:
            self.client.stop()
            self.client = None

    def restart(self):
        """重启桥接：配置变更后调用。"""
        self.stop()
        return self.start()

    def report(self, payload):
        """处理抽屉上报。未启动或无客户端时直接返回 0。"""
        cfg = bridge_store.get_config()
        if not cfg.get("enabled"):
            return 0
        return message_router.handle_report(self.client, payload)

    def status(self):
        """返回桥接状态，供设置页展示与排查。

        connected 取客户端的 _ws_connected（真正连上才为真），
        而不是 _running（只表示尝试启动过）——否则指示灯会虚亮，
        让人误以为连接正常。
        lastEvent 为最近收到的事件类型，空表示网关没推事件过来。
        """
        cfg = bridge_store.get_config()
        connected = bool(self.client and getattr(self.client, "_ws_connected", False))
        last_event = getattr(self.client, "_last_event", "") if self.client else ""
        return {
            "enabled": bool(cfg.get("enabled")),
            "connected": connected,
            "appId": cfg.get("app_id") or "",
            "push": cfg.get("push") or {},
            "lastEvent": last_event,
            # 当前实际订阅的事件位，便于对照官网核对
            "intents": getattr(self.client, "intents", 0) if self.client else 0,
        }


# 全局单例
bridge = RemoteBridge()


def init_bridge():
    """服务启动时的初始化入口：按配置决定是否拉起长连接。

    失败不阻断 Flask 启动——桥接是可选功能，
    凭证未填或依赖未装时，其余工具功能照常可用。
    """
    try:
        return bridge.start()
    except Exception as e:
        log("初始化异常（不阻断服务启动）：", e)
        return False
