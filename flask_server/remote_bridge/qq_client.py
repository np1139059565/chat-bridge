"""远程桥接 —— QQ 机器人协议层

职责：
1. 用 AppID + AppSecret 换 access_token（带过期时间与自动续期）
2. 建立 WebSocket 长连接，维持心跳、断线重连
3. 把收到的 C2C 消息事件回调给上层（qq_gateway）
4. 通过 HTTP 发送被动回复消息

本文件的接口域名、intents 位、事件字段名已对照 QQ 开放平台官方文档核对确认：
  - 接口域名 API_BASE = https://api.sgroup.qq.com
  - 取 token 地址与请求体字段名（appId / clientSecret）
  - 网关地址获取接口 GET /gateway
  - intents 取值（C2C 单聊消息所需位 = 1 << 25）
  - 发送消息的接口路径与消息体结构（POST /v2/users/{openid}/messages）
如遇平台协议调整，以官方文档最新版本为准。

依赖：websocket-client（未安装时降级为不启动，不影响服务其余功能）
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request

from .qq_media import QqMediaMixin
import app_log

try:
    import websocket  # websocket-client
    HAS_WS = True
except ImportError:
    websocket = None
    HAS_WS = False

# ---------- 接口地址（已核对官方文档） ----------
API_BASE = "https://api.sgroup.qq.com"          # 正式环境
TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
GATEWAY_URL = API_BASE + "/gateway"
# 沙箱环境（测试用）：https://sandbox.api.sgroup.qq.com

# 单聊消息所需的 intents（已核对官方文档）
# C2C_MESSAGE_CREATE（单聊消息）属于 GROUP_AND_C2C_EVENT = 1 << 25；
# 1 << 30 是 PUBLIC_MESSAGES（公域消息，频道用），不含单聊——
# 用错该位会出现「连上、收到 READY、却收不到单聊消息」。
# 可用 remote_bridge.yaml 的 intents 覆盖此缺省值。
DEFAULT_INTENTS = 1 << 25

# 网关操作码
OP_DISPATCH = 0      # 服务端派发事件
OP_HEARTBEAT = 1     # 客户端心跳
OP_IDENTIFY = 2      # 客户端鉴权
OP_RESUME = 6        # 恢复会话
OP_RECONNECT = 7     # 服务端要求重连
OP_INVALID = 9       # 鉴权失败
OP_HELLO = 10        # 服务端握手，返回心跳间隔
OP_HEARTBEAT_ACK = 11


def log(*args):
    """统一前缀打印，便于在服务端控制台过滤桥接日志。"""
    app_log.info("[bridge][qq]", *args)


def _c2c_body(content, msg_id, msg_seq, markdown):
    """构造单聊被动回复的请求体（文本 / Markdown 两种形态）。

    Markdown 消息：msg_type=2，正文放进 markdown.content，content 必须为空串；
    纯文本消息：msg_type=0，正文直接放在 content。
    @param content  消息文本
    @param msg_id   被动回复引用的用户消息 id
    @param msg_seq  同一 msg_id 下的消息序号
    @param markdown 是否按 Markdown 发送
    @returns 请求体字典
    """
    if markdown:
        return {
            "msg_type": 2,                          # 2 = Markdown
            "markdown": {"content": content},      # Markdown 正文
            "content": "",                         # 此模式下必须留空
            "msg_id": msg_id,                       # 被动回复引用的用户消息 id
            "msg_seq": msg_seq,                     # 同 msg_id 下的去重序号
        }
    return {
        "content": content,
        "msg_type": 0,            # 0 = 文本
        "msg_id": msg_id,         # 被动回复引用的用户消息 id
        "msg_seq": msg_seq,       # 同 msg_id 下的去重序号
    }


class QQClient(QqMediaMixin):
    """QQ 机器人客户端：token 管理 + WebSocket 长连接。

    富媒体（图片 / 语音）发送能力由 QqMediaMixin 提供（见 qq_media.py）。
    """

    def __init__(self, app_id, app_secret, on_event, intents=None):
        """
        @param app_id     机器人 AppID
        @param app_secret 机器人 AppSecret
        @param on_event   收到事件时的回调，入参 (event_type, data)
        @param intents    订阅的事件位；缺省用 DEFAULT_INTENTS（单聊消息）
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self.on_event = on_event
        self.intents = intents if intents else DEFAULT_INTENTS
        self._token = ""
        self._token_expire = 0        # token 过期时间戳（秒）
        self._ws = None
        self._thread = None
        self._hb_thread = None
        self._running = False
        self._ws_connected = False    # WebSocket 是否真正连上（_on_open 置真，_on_close 置假）
        self._last_event = ""         # 最近收到的事件类型，便于诊断「事件是否下发」
        self._seq = None              # 最近一次事件的序号，用于心跳与恢复
        self._session_id = ""

    # ---------- token ----------
    def _http_post(self, url, body, headers=None):
        """发一个 JSON POST；返回解析后的 dict。失败抛异常。"""
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _http_get(self, url, headers=None):
        """发一个 GET；返回解析后的 dict。失败抛异常。"""
        req = urllib.request.Request(url, method="GET")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def refresh_token(self):
        """获取 / 刷新 access_token。成功返回 True。"""
        try:
            # 请求体字段名：appId / clientSecret（已核对官方文档）
            resp = self._http_post(TOKEN_URL, {
                "appId": self.app_id,
                "clientSecret": self.app_secret,
            })
            self._token = resp.get("access_token") or ""
            # expires_in 单位为秒；提前 60 秒视为过期，留出续期余量
            expire_in = int(resp.get("expires_in") or 0)
            self._token_expire = time.time() + max(0, expire_in - 60)
            if not self._token:
                log("取 token 失败：响应中无 access_token")
                return False
            log("token 已获取，有效期约", expire_in, "秒")
            return True
        except Exception as e:
            log("取 token 异常：", e)
            return False

    def _ensure_token(self):
        """确保 token 有效；临近过期或为空时刷新。"""
        if not self._token or time.time() >= self._token_expire:
            return self.refresh_token()
        return True

    def _auth_header(self):
        """构造鉴权头。"""
        return {"Authorization": "QQBot " + self._token}

    # ---------- 网关地址 ----------
    def _get_gateway(self):
        """取 WebSocket 网关地址；失败返回空串。

        关键：取网关前必须先确保 token 有效。
        token 有效期约 2 小时，而断线重连循环只调本函数、不调 start()，
        若不在此刷新，就会带着过期 token 反复取网关、永远 401，
        陷入「每 5 秒重试一次、始终连不上」的死循环。
        """
        if not self._ensure_token():
            return ""
        try:
            resp = self._http_get(GATEWAY_URL, self._auth_header())
            return resp.get("url") or ""
        except urllib.error.HTTPError as e:
            # 401：token 可能被服务端提前作废。清空它，
            # 下次 _ensure_token 会重新获取，避免一直用废 token 重试。
            if e.code == 401:
                log("取网关 401，清空 token 待重新获取")
                self._token = ""
            log("取网关地址失败：", e)
            return ""
        except Exception as e:
            log("取网关地址失败：", e)
            return ""

    # ---------- 发送消息 ----------
    @staticmethod
    def _http_error_detail(e):
        """提取 HTTPError 的响应体详情（服务端返回的错误说明）。

        读取失败不抛错，返回空串：诊断信息缺失不应盖过「请求失败」这个主结果。
        """
        try:
            return e.read().decode("utf-8")
        except Exception:
            return ""

    def send_c2c(self, openid, content, msg_id="", msg_seq=1, markdown=False):
        """发送单聊被动回复。

        被动回复必须携带 msg_id（即收到的那条用户消息的 id），
        且需在收到后的一段时间内发出（窗口约 60 分钟）。
        @param openid   接收方用户 openid
        @param content  消息文本
        @param msg_id   被动回复所引用的用户消息 id
        @param msg_seq  同一 msg_id 下的消息序号，多条回复需递增
        @param markdown 是否按 Markdown 消息发送：真走 msg_type=2，假走 msg_type=0
        @returns (ok, data_or_error)
        """
        if not self._ensure_token():
            return False, "no_token"
        # 单聊发送接口路径（两种消息类型共用同一路径）
        url = API_BASE + "/v2/users/%s/messages" % openid
        body = _c2c_body(content, msg_id, msg_seq, markdown)
        try:
            resp = self._http_post(url, body, self._auth_header())
            return True, resp
        except urllib.error.HTTPError as e:
            return False, "HTTP %s %s" % (e.code, self._http_error_detail(e))
        except Exception as e:
            return False, str(e)

    # ---------- WebSocket ----------
    def start(self):
        """启动长连接（后台线程）。重复调用幂等。"""
        if not HAS_WS:
            log("未安装 websocket-client，桥接不启动")
            return False
        if self._running:
            return True
        if not self._ensure_token():
            return False
        self._running = True
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """停止长连接。"""
        self._running = False
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass
        self._ws = None

    def _run_forever(self):
        """连接循环：断线后按固定间隔重连，直到 stop()。"""
        while self._running:
            url = self._get_gateway()
            if not url:
                log("5 秒后重试取网关地址")
                time.sleep(5)
                continue
            try:
                self._ws = websocket.WebSocketApp(
                    url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever()
            except Exception as e:
                log("连接异常：", e)
            if self._running:
                log("5 秒后重连")
                time.sleep(5)

    def _on_open(self, ws):
        """连接建立后发送鉴权包。"""
        self._ws_connected = True
        log("WebSocket 已连接，发送鉴权")
        payload = {
            "op": OP_IDENTIFY,
            "d": {
                "token": "QQBot " + self._token,
                "intents": self.intents,
                "shard": [0, 1],
                "properties": {},
            },
        }
        ws.send(json.dumps(payload))

    def _close_ws(self, ws):
        """关闭连接，忽略关闭过程中的异常。"""
        try:
            ws.close()
        except Exception:
            pass

    def _op_hello(self, ws, msg):
        """握手：按服务端给的心跳间隔启动心跳线程。"""
        interval = (msg.get("d") or {}).get("heartbeat_interval", 30000) / 1000.0
        self._start_heartbeat(ws, interval)

    def _op_reconnect(self, ws, msg):
        """服务端要求重连：关闭当前连接，交由连接循环重连。"""
        log("服务端要求重连")
        self._close_ws(ws)

    def _op_invalid(self, ws, msg):
        """鉴权失败：清空 token 后关闭连接，下次会重新获取 token。"""
        log("鉴权失败，刷新 token 后重连")
        self._token = ""
        self._close_ws(ws)

    def _op_dispatch(self, ws, msg):
        """事件派发：更新序号与最近事件类型，交给上层 on_event 处理。"""
        self._seq = msg.get("s") or self._seq
        t = msg.get("t") or ""
        d = msg.get("d") or {}
        # 记录最近事件类型：诊断「事件是否下发」的关键线索。
        # 若这里始终为空，说明网关没把事件推来（多半是 intents 或鉴权问题）。
        self._last_event = t
        log("收到事件", t)
        try:
            self.on_event(t, d)
        except Exception as e:
            log("事件处理异常：", e)

    # op → 处理函数。心跳确认（OP_HEARTBEAT_ACK）无需动作，不登记即为忽略。
    _OP_HANDLERS = None  # 见 __init__ 之后的 _bind_op_handlers：需绑定实例方法，故延迟构建

    def _op_heartbeat_ack(self, ws, msg):
        """心跳确认：无需动作。"""

    def _on_message(self, ws, raw):
        """处理服务端下行数据：解析后按 op 查表分派。"""
        try:
            msg = json.loads(raw)
        except Exception:
            return
        handlers = self._op_handler_table()
        fn = handlers.get(msg.get("op"))
        if fn:
            fn(ws, msg)

    def _op_handler_table(self):
        """构建 op → 绑定方法的映射表（首次调用时构建并缓存）。"""
        if self._OP_HANDLERS is None:
            self._OP_HANDLERS = {
                OP_HELLO: self._op_hello,
                OP_HEARTBEAT_ACK: self._op_heartbeat_ack,
                OP_RECONNECT: self._op_reconnect,
                OP_INVALID: self._op_invalid,
                OP_DISPATCH: self._op_dispatch,
            }
        return self._OP_HANDLERS

    def _start_heartbeat(self, ws, interval):
        """启动心跳线程：按服务端给的时间间隔发送心跳包。"""
        def beat():
            while self._running and self._ws is ws:
                try:
                    ws.send(json.dumps({"op": OP_HEARTBEAT, "d": self._seq}))
                except Exception:
                    break
                time.sleep(interval)
        if self._hb_thread and self._hb_thread.is_alive():
            return
        self._hb_thread = threading.Thread(target=beat, daemon=True)
        self._hb_thread.start()

    def _on_error(self, ws, err):
        log("连接错误：", err)

    def _on_close(self, ws, code, reason):
        self._ws_connected = False
        log("连接关闭：", code, reason)
