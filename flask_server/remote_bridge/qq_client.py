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
import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request

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
    print("[bridge][qq]", *args)


class QQClient:
    """QQ 机器人客户端：token 管理 + WebSocket 长连接。"""

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
    def send_c2c(self, openid, content, msg_id="", msg_seq=1):
        """发送单聊被动回复。

        被动回复必须携带 msg_id（即收到的那条用户消息的 id），
        且需在收到后的一段时间内发出（窗口约 60 分钟）。
        @param openid  接收方用户 openid
        @param content 消息文本
        @param msg_id  被动回复所引用的用户消息 id
        @param msg_seq 同一 msg_id 下的消息序号，多条回复需递增
        @returns (ok, data_or_error)
        """
        if not self._ensure_token():
            return False, "no_token"
        # 单聊发送接口路径与请求体结构（已核对官方文档）
        url = API_BASE + "/v2/users/%s/messages" % openid
        body = {
            "content": content,
            "msg_type": 0,            # 0 文本；2 为 Markdown（需平台开通）
            "msg_id": msg_id,         # 被动回复引用的用户消息 id
            "msg_seq": msg_seq,       # 同 msg_id 下的去重序号
        }
        try:
            resp = self._http_post(url, body, self._auth_header())
            return True, resp
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8")
            except Exception:
                pass
            return False, "HTTP %s %s" % (e.code, detail)
        except Exception as e:
            return False, str(e)

    def send_c2c_image(self, openid, image_path, msg_id="", msg_seq=1):
        """发送单聊图片（富媒体）。

        用本地文件直接上传，无需公网地址：
        读文件 → Base64 编码 → 作为 file_data 上传拿 file_info → 发 msg_type=7。
        官方上传接口支持 url 与 file_data 二选一；用 file_data 就绕开了
        「QQ 服务器来取图」对公网地址的依赖。
        上传接口路径、file_type 取值、msg_type=7 的消息体结构已核对官方文档。
        @param openid     接收方用户 openid
        @param image_path 本地图片文件路径
        @param msg_id     被动回复引用的用户消息 id
        @param msg_seq    同一 msg_id 下的序号
        @returns (ok, data_or_error)
        """
        if not self._ensure_token():
            return False, "no_token"
        # 读文件并 Base64 编码
        try:
            with open(image_path, "rb") as f:
                raw = f.read()
        except Exception as e:
            return False, "read_file_failed: %s" % e
        b64 = base64.b64encode(raw).decode("ascii")
        # 第一步：上传富媒体，拿 file_info
        upload_url = API_BASE + "/v2/users/%s/files" % openid
        try:
            up = self._http_post(upload_url, {
                "file_type": 1,          # 1 = 图片
                "file_data": b64,        # 本地文件内容，免公网地址
                "srv_send_msg": False,   # 不自动发送，只返回 file_info
            }, self._auth_header())
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8")
            except Exception:
                pass
            return False, "upload HTTP %s %s" % (e.code, detail)
        except Exception as e:
            return False, str(e)
        file_info = (up or {}).get("file_info") or ""
        if not file_info:
            return False, "no_file_info"
        # 第二步：发送富媒体消息
        url = API_BASE + "/v2/users/%s/messages" % openid
        body = {
            "content": "",
            "msg_type": 7,           # 7 = 富媒体
            "media": {"file_info": file_info},
            "msg_id": msg_id,
            "msg_seq": msg_seq,
        }
        try:
            resp = self._http_post(url, body, self._auth_header())
            return True, resp
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8")
            except Exception:
                pass
            return False, "send HTTP %s %s" % (e.code, detail)
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

    def _on_message(self, ws, raw):
        """处理服务端下行数据。"""
        try:
            msg = json.loads(raw)
        except Exception:
            return
        op = msg.get("op")
        # 握手：返回心跳间隔，启动心跳线程
        if op == OP_HELLO:
            interval = (msg.get("d") or {}).get("heartbeat_interval", 30000) / 1000.0
            self._start_heartbeat(ws, interval)
            return
        # 心跳确认
        if op == OP_HEARTBEAT_ACK:
            return
        # 服务端要求重连
        if op == OP_RECONNECT:
            log("服务端要求重连")
            try:
                ws.close()
            except Exception:
                pass
            return
        # 鉴权失败
        if op == OP_INVALID:
            log("鉴权失败，刷新 token 后重连")
            self._token = ""
            try:
                ws.close()
            except Exception:
                pass
            return
        # 事件派发
        if op == OP_DISPATCH:
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
