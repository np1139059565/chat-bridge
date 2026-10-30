"""远程桥接 —— 企业微信智能机器人客户端

职责：
1. 建立并维持 WebSocket 长连接（订阅、心跳、断线重连）
2. 接收消息回调，交给上层网关
3. 回复消息（透传回调的 req_id）
4. 主动推送（aibot_send_msg）
5. 媒体上传（图片 / 文件）与接收侧解密落盘

与微信 ClawBot 的架构差异：
  ClawBot  —— 主动长轮询拉消息，无主动推送，图片发送未实现
  企业微信 —— WebSocket 长连接，支持主动推送、图片、文件

线程模型：
  用 websocket-client（同步）跑后台线程，与 qq_client 保持同一套模型。
  不使用 asyncio——本工程是 Flask 同步架构，引入事件循环会多出一层
  生命周期管理，排查成本高。

硬约束（官方文档）：
  - 每个机器人同一时刻只允许一条长连接，新连接会踢掉旧连接
  - 心跳间隔 30 秒，否则连接被回收
  - 回复窗口 24 小时
"""
import base64
import json
import os
import threading
import time

import app_log
from . import wecom_proto as proto
from .wecom_media import WecomMediaMixin


def log(*args):
    """统一前缀打印，便于在服务端控制台过滤企业微信日志。"""
    app_log.info("[bridge][wecom]", *args)


try:
    import websocket  # websocket-client
    HAS_WS = True
except ImportError:
    websocket = None
    HAS_WS = False


class WecomClient(WecomMediaMixin):
    """企业微信智能机器人客户端。

    媒体收发能力（图片/文件）由 WecomMediaMixin 提供（见 wecom_media.py）。
    """

    # 是否需要被动回复窗口：企业微信靠 chatid 主动投递，不依赖窗口
    needs_window = False

    # 单条文本上限：企业微信对 markdown 有长度限制，超长会被截断或拒绝
    MAX_TEXT_CHARS = 4000

    def __init__(self, bot_id, secret, on_message):
        """
        @param bot_id     机器人 id
        @param secret     机器人密钥
        @param on_message 收到消息时的回调，入参 (client, msg)
        """
        self.bot_id = bot_id
        self.secret = secret
        self.on_message = on_message
        self._ws = None
        self._thread = None
        self._hb_thread = None
        self._running = False
        self._connected = False      # 订阅是否成功
        self._last_event = ""        # 最近事件类型，供状态展示
        self._lock = threading.RLock()
        # 待响应的上传任务：{req_id: 结果}，用于把异步回包交还给等待方
        self._pending = {}
        # 订阅请求的 req_id：成功应答靠它比对（应答顶层没有 cmd 字段）
        self._subscribe_req_id = ""

    # ---------- 状态 ----------
    def has_cred(self):
        """是否已配置凭证。"""
        return bool(self.bot_id and self.secret)

    # ---------- 连接 ----------
    def start(self):
        """启动长连接（后台线程）。重复调用幂等。

        @returns 是否成功启动
        """
        if not HAS_WS:
            log("未安装 websocket-client，企业微信通道不启动")
            return False
        if not self.has_cred():
            log("缺少 BotID / Secret，企业微信通道不启动")
            return False
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """停止长连接。"""
        self._running = False
        self._connected = False
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass
        self._ws = None

    def _run_forever(self):
        """连接循环：断线后按固定间隔重连，直到 stop()。"""
        while self._running:
            try:
                self._connect_once()
            except Exception as e:
                log("连接异常：", e)
            if self._running:
                log("%d 秒后重连" % proto.RECONNECT_DELAY)
                time.sleep(proto.RECONNECT_DELAY)

    def _connect_once(self):
        """建立一次连接并阻塞运行到断开。"""
        log("正在连接企业微信长连接")
        self._ws = websocket.WebSocketApp(
            proto.WSS_URL,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._ws.run_forever()

    def _on_open(self, ws):
        """连接建立后发送订阅帧，并记下 req_id 用于识别成功应答。

        为什么要记 req_id：成功应答的结构是 {headers:{req_id}, errcode:0, errmsg:"ok"}，
        顶层**没有 cmd 字段**。曾按 cmd 判断订阅成功，条件永远为假，
        导致订阅明明成功、连接状态却一直是未连接，心跳也不启动。
        """
        log("WebSocket 已连接，发送订阅")
        try:
            req_id = proto.new_req_id()
            with self._lock:
                self._subscribe_req_id = req_id
            ws.send(proto.frame(proto.CMD_SUBSCRIBE,
                                {"bot_id": self.bot_id, "secret": self.secret},
                                req_id=req_id))
        except Exception as e:
            log("发送订阅失败：", e)

    def _on_error(self, ws, err):
        log("连接错误：", err)

    def _on_close(self, ws, code, reason):
        self._connected = False
        log("连接关闭：", code, reason)

    def _on_message(self, ws, raw):
        """处理下行帧：按 cmd 分派。

        先记一行原始帧日志：企业微信的下行格式与文档不完全一致
        （订阅应答顶层就没有 cmd 字段），排障时必须看真实数据而非猜测。
        """
        try:
            log("收到下行帧：", str(raw)[:400])
        except Exception:
            pass
        try:
            msg = json.loads(raw)
        except Exception:
            return
        cmd = msg.get("cmd") or ""
        # 订阅响应：errcode 为 0 表示成功
        if cmd == proto.CMD_SUBSCRIBE or msg.get("errcode") is not None:
            self._handle_ack(msg)
            return
        if cmd == proto.CMD_MSG_CALLBACK:
            self._handle_msg(msg)
            return
        if cmd == proto.CMD_EVENT_CALLBACK:
            self._last_event = "event"
            return
        # 上传类回包交给等待方
        self._handle_ack(msg)

    def _handle_ack(self, msg):
        """处理应答帧：订阅结果、上传结果等。

        识别订阅成功必须靠 req_id 比对，不能靠 cmd：
        成功应答的结构是 {headers:{req_id}, errcode:0, errmsg:"ok"}，
        顶层没有 cmd 字段。曾按 cmd 判断，条件恒假，导致订阅成功
        却始终显示未连接、心跳也没启动。
        """
        req_id = ((msg.get("headers") or {}).get("req_id")) or ""
        errcode = msg.get("errcode")
        if errcode is not None and errcode != 0:
            log("应答错误：errcode=%s errmsg=%s" % (errcode, msg.get("errmsg")))
        # 订阅应答：比对发订阅时记下的 req_id
        with self._lock:
            is_subscribe = bool(req_id) and req_id == self._subscribe_req_id
        if is_subscribe:
            if errcode == 0:
                if not self._connected:
                    self._connected = True
                    self._last_event = "subscribed"
                    log("订阅成功")
                    self._start_heartbeat()
            else:
                # 订阅被拒：标记未连接，由连接循环重试
                self._connected = False
                log("订阅被拒绝，将重试")
            return
        # 其它应答：唤醒等待方（上传等）
        with self._lock:
            slot = self._pending.pop(req_id, None)
        if slot is not None:
            slot["result"] = msg
            slot["event"].set()

    def _handle_msg(self, msg):
        """处理消息回调，交给上层。"""
        self._last_event = "message"
        try:
            if self.on_message:
                self.on_message(self, msg)
        except Exception as e:
            log("消息处理异常：", e)

    def _start_heartbeat(self):
        """启动心跳线程：每 30 秒发一次 ping。"""
        def beat():
            while self._running and self._connected:
                time.sleep(proto.HEARTBEAT_INTERVAL)
                if not self._running:
                    return
                try:
                    if self._ws:
                        self._ws.send(proto.frame(proto.CMD_PING))
                except Exception:
                    return
        if self._hb_thread and self._hb_thread.is_alive():
            return
        self._hb_thread = threading.Thread(target=beat, daemon=True)
        self._hb_thread.start()

    # ---------- 收发 ----------
    def _send_wait(self, frame_text, req_id, timeout=30):
        """发送一帧并等待同 req_id 的应答。

        @param frame_text 帧文本
        @param req_id     请求 id（用于匹配应答）
        @param timeout    等待超时秒数
        @returns 应答字典；超时返回空字典
        """
        if not self._ws:
            return {}
        slot = {"event": threading.Event(), "result": None}
        with self._lock:
            self._pending[req_id] = slot
        try:
            self._ws.send(frame_text)
        except Exception as e:
            log("发送失败：", e)
            with self._lock:
                self._pending.pop(req_id, None)
            return {}
        slot["event"].wait(timeout)
        with self._lock:
            self._pending.pop(req_id, None)
        return slot["result"] or {}

    def _send_nowait(self, frame_text):
        """发送一帧，不等待应答。

        @param frame_text 帧文本
        @returns 是否发送成功
        """
        if not self._ws:
            return False
        try:
            self._ws.send(frame_text)
            return True
        except Exception as e:
            log("发送失败：", e)
            return False

    def respond(self, msg, content, chat_type=None, msgtype="markdown"):
        """回复一条消息（透传回调的 req_id）。

        req_id 必须用回调带来的那个，否则回复关联不上原会话。

        @param msg       回调的消息体
        @param content    正文
        @param chat_type 会话类型；缺省取回调里的
        @param msgtype   消息类型
        @returns 是否发送成功
        """
        req_id = msg.get("req_id") or ""
        body = msg.get("body") or msg
        # 单聊消息没有 chatid，只有 from.userid，用它作会话标识
        frm = body.get("from") or {}
        chatid = body.get("chatid") or frm.get("userid") or ""
        ct = chat_type or body.get("chat_type") or proto.CHAT_SINGLE
        if not content:
            return False
        text = str(content)
        if len(text) > self.MAX_TEXT_CHARS:
            text = text[:self.MAX_TEXT_CHARS - 20] + "\n…（内容过长已截断）"
        frame_text = proto.respond_frame(req_id, chatid, text,
                                         chat_type=ct, msgtype=msgtype)
        return self._send_nowait(frame_text)

    def respond_to(self, req_id, chatid, content, chat_type=proto.CHAT_SINGLE,
                   msgtype="markdown"):
        """针对某条用户消息回复（而不是主动推送）。

        为什么必须用它而不是 send_msg：用户发消息后，企业微信客户端会进入
        「等待机器人回复」状态并转圈。只有收到带**原消息 req_id** 的
        aibot_respond_msg，客户端才认为处理完成、停止转圈。
        用 aibot_send_msg 主动推送，消息能到达，但原消息永远停在发送中。

        @param req_id    原消息的请求 id（必须原样透传）
        @param chatid    会话 id
        @param content   正文
        @param chat_type 会话类型
        @param msgtype   消息类型
        @returns (ok, data_or_error)
        """
        if not req_id or not chatid:
            return False, "missing_req_id_or_chatid"
        text = str(content or "")
        if not text:
            return False, "empty_text"
        if len(text) > self.MAX_TEXT_CHARS:
            text = text[:self.MAX_TEXT_CHARS - 20] + "\n…（内容过长已截断）"
        frame_text = proto.respond_frame(req_id, chatid, text,
                                         chat_type=chat_type, msgtype=msgtype)
        ok = self._send_nowait(frame_text)
        return ok, ({} if ok else "send_failed")

    def send_text(self, chatid, text, chat_type=proto.CHAT_SINGLE):
        """主动推送一条文本（QQ 兼容签名）。

        参数名与 QQ 客户端对齐，使指令层无需改动即可复用。

        @param chatid    会话 id
        @param text      正文
        @param chat_type 会话类型
        @returns (ok, data_or_error)
        """
        return self.send_markdown(chatid, text, chat_type)

    def send_c2c(self, openid, content, msg_id="", msg_seq=1, markdown=False):
        """兼容 QQ 客户端签名的发送入口。

        @param openid   会话 id
        @param content  正文
        @param msg_id   忽略
        @param msg_seq  忽略
        @param markdown 忽略（企业微信统一按 markdown 发送）
        @returns (ok, data_or_error)
        """
        return self.send_markdown(openid, content)

    def send_markdown(self, chatid, content, chat_type=proto.CHAT_SINGLE):
        """主动推送 markdown 消息。

        @param chatid    会话 id
        @param content   正文
        @param chat_type 会话类型
        @returns (ok, data_or_error)
        """
        if not chatid:
            return False, "no_chatid"
        text = str(content or "")
        if not text:
            return False, "empty_text"
        if len(text) > self.MAX_TEXT_CHARS:
            text = text[:self.MAX_TEXT_CHARS - 20] + "\n…（内容过长已截断）"
        frame_text = proto.send_frame(chatid, chat_type,
                                      {"msgtype": "markdown",
                                       "markdown": {"content": text}})
        ok = self._send_nowait(frame_text)
        return ok, ({} if ok else "send_failed")

    # ---------- 媒体（图片/文件）----------
    # 实现见 wecom_media.WecomMediaMixin，由本类继承。

