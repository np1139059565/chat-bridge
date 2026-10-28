"""远程桥接 —— 微信 ClawBot（iLink）客户端

职责：
1. 凭证管理（扫码登录所得，落盘权限 600）
2. 长轮询 getupdates 拉取消息（游标落盘，重启不重放）
3. 通过 sendmessage 发送文本 / 富媒体
4. 维护每个用户的 context_token（发送时必须原样回传）

协议常量与 HTTP 细节在 weixin_proto（协议基础层），本文件只做业务编排。

配额约束（决定上层怎么写）：
  - 用户发消息后 24 小时内可回复
  - 24 小时内最多 10 条独立消息，每条用户消息重置计数
  - 不支持主动推送，不支持群聊

设计说明：
  仅依赖标准库 urllib，与 qq_client 保持一致，不引入新依赖。
  同步实现、后台线程跑长轮询，与 Flask 的同步架构吻合。
"""
import json
import os
import threading
import time
import urllib.error
import uuid

import app_log
from . import weixin_proto as proto


def log(*args):
    """统一前缀打印，便于在服务端控制台过滤微信桥接日志。"""
    app_log.info("[bridge][weixin]", *args)


class WeixinClient:
    """微信 ClawBot 客户端：扫码登录 + 长轮询 + 发送消息。"""

    def __init__(self, cred_path, buf_path, on_message):
        """
        @param cred_path 凭证文件路径（含 bot_token，权限 600）
        @param buf_path  长轮询游标文件路径（防重启重放）
        @param on_message 收到消息时的回调，入参 (client, msg)
        """
        self.cred_path = str(cred_path)
        self.buf_path = str(buf_path)
        self.on_message = on_message
        self._cred = None            # 凭证：{token, base_url, bot_id, user_id}
        self._running = False
        self._thread = None
        self._ws_connected = False   # 供状态展示：长轮询是否在正常运行
        self._last_event = ""        # 最近收到的事件描述，便于诊断
        self._buf = ""               # 长轮询游标
        self._context = {}           # {用户id: context_token}，发送时必须回传
        self._lock = threading.RLock()

    # ---------- 凭证 ----------
    def load_cred(self):
        """从磁盘读取凭证；不存在或损坏返回 None。"""
        if not os.path.exists(self.cred_path):
            return None
        try:
            with open(self.cred_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            if data.get("token"):
                self._cred = data
                return data
        except Exception as e:
            log("读取凭证失败：", e)
        return None

    def save_cred(self, cred):
        """把凭证写入磁盘，权限设为仅本人可读写。

        凭证含 bot_token，属敏感数据：目录 700、文件 600。
        Windows 上 chmod 语义有限，失败不阻断登录。
        @param cred 凭证字典
        """
        try:
            os.makedirs(os.path.dirname(self.cred_path), mode=0o700, exist_ok=True)
            with open(self.cred_path, "w", encoding="utf-8") as f:
                json.dump(cred, f, ensure_ascii=False)
            try:
                os.chmod(self.cred_path, 0o600)
            except OSError:
                pass
            self._cred = cred
        except Exception as e:
            log("写入凭证失败：", e)

    def clear_cred(self):
        """清除凭证文件（session 过期时调用，迫使重新扫码）。"""
        self._cred = None
        try:
            if os.path.exists(self.cred_path):
                os.remove(self.cred_path)
        except OSError as e:
            log("删除凭证失败：", e)

    def has_cred(self):
        """是否已有可用凭证。"""
        return bool(self._cred and self._cred.get("token"))

    def _base(self):
        """取实际 API 基地址：登录成功后可能下发地域地址。"""
        return (self._cred or {}).get("base_url") or proto.DEFAULT_BASE

    def _url(self, path):
        """按当前基地址拼接完整接口地址。"""
        return proto.join_url(self._base(), path)

    # ---------- 扫码登录 ----------
    def fetch_qrcode(self, base="", bot_type=proto.DEFAULT_BOT_TYPE):
        """取登录二维码。

        @param base     基地址；为空用默认地址
        @param bot_type 通道构建类型，固定 3
        @returns {qrcode, qrcode_img_content}
        """
        path = "ilink/bot/get_bot_qrcode?bot_type=" + str(bot_type)
        return proto.request(proto.join_url(base, path),
                             body={"local_token_list": self._local_tokens()})

    def _local_tokens(self):
        """取本地已有令牌列表，供服务端识别「已绑定」并走快速路径。"""
        tok = (self._cred or {}).get("token")
        return [tok] if tok else []

    def poll_qrcode_status(self, qrcode, base="", verify_code=""):
        """查询一次扫码状态（长轮询，客户端超时视为等待）。

        @param qrcode      二维码标识
        @param base        基地址
        @param verify_code 手机显示的数字验证码（需要时）
        @returns 状态字典
        """
        import urllib.parse
        path = "ilink/bot/get_qrcode_status?qrcode=" + urllib.parse.quote(qrcode)
        if verify_code:
            path += "&verify_code=" + urllib.parse.quote(str(verify_code))
        try:
            return proto.request(proto.join_url(base, path), method="GET",
                                 timeout=proto.QR_POLL_TIMEOUT)
        except Exception as e:
            # 网络错误与网关超时都按「继续等待」处理，与官方一致
            log("查询扫码状态异常（按等待处理）：", e)
            return {"status": "wait"}

    # ---------- 长轮询接收 ----------
    def _load_buf(self):
        """从磁盘读取长轮询游标。"""
        try:
            if os.path.exists(self.buf_path):
                with open(self.buf_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
        except Exception as e:
            log("读取游标失败：", e)
        return ""

    def _save_buf(self, buf):
        """把游标写盘。

        必须落盘：否则进程重启会从头拉，把历史消息重复处理一遍。
        @param buf 新游标
        """
        if not buf:
            return
        try:
            os.makedirs(os.path.dirname(self.buf_path), exist_ok=True)
            with open(self.buf_path, "w", encoding="utf-8") as f:
                f.write(buf)
        except Exception as e:
            log("写入游标失败：", e)

    def get_updates(self):
        """拉取一批新消息。

        长轮询超时属正常现象，返回空消息列表即可，由调用方继续下一轮。
        @returns 响应字典 {ret, msgs, get_updates_buf}
        """
        token = (self._cred or {}).get("token") or ""
        body = {"get_updates_buf": self._buf or "", "base_info": proto.base_info()}
        try:
            resp = proto.request(self._url("ilink/bot/getupdates"), body=body,
                                 token=token, timeout=proto.LONG_POLL_TIMEOUT)
        except Exception as e:
            # urllib 超时与官方 AbortError 语义一致：正常返回空结果
            log("长轮询超时或异常（正常现象）：", str(e)[:120])
            return {"ret": 0, "msgs": [], "get_updates_buf": self._buf}
        return resp or {}

    # ---------- 上下文令牌 ----------
    def set_context(self, user_id, context_token):
        """记住某用户的上下文令牌。

        发送时必须原样回传它，否则消息会投递到错误窗口或直接被拒。
        @param user_id       用户标识
        @param context_token 上下文令牌
        """
        if user_id and context_token:
            with self._lock:
                self._context[user_id] = context_token

    def get_context(self, user_id):
        """取某用户的上下文令牌。"""
        with self._lock:
            return self._context.get(user_id) or ""

    # ---------- 发送 ----------
    def _send_items(self, to_user, items, context_token=""):
        """发送一组消息项。

        每次请求只带一个消息项：官方实现刻意如此，避免一条请求里混多个项
        导致部分项被丢弃。
        @param to_user       接收方用户标识
        @param items         消息项列表
        @param context_token 上下文令牌
        @returns (ok, data_or_error)
        """
        token = (self._cred or {}).get("token") or ""
        if not token:
            return False, "no_token"
        ok = True
        last = None
        for item in items:
            body = {"msg": {
                "from_user_id": "",
                "to_user_id": to_user,
                "client_id": uuid.uuid4().hex,
                "message_type": proto.MSG_TYPE_BOT,
                "message_state": proto.MSG_STATE_FINISH,
                "item_list": [item],
            }, "base_info": proto.base_info()}
            if context_token:
                body["msg"]["context_token"] = context_token
            try:
                resp = proto.request(self._url("ilink/bot/sendmessage"),
                                     body=body, token=token)
                last = resp
                # 有明确错误码即视为失败，但继续尝试其余项
                if resp.get("errcode") or str(resp.get("ret")) not in ("0", "None", ""):
                    ok = False
            except urllib.error.HTTPError as e:
                ok = False
                last = "HTTP %s %s" % (e.code, proto.read_http_error(e))
            except Exception as e:
                ok = False
                last = str(e)
        return ok, last

    def send_text(self, to_user, text, context_token=""):
        """发送一条文本消息。

        上层必须保证「一条用户消息只回一条」，这是配额约束下的硬要求。
        @param to_user       接收方
        @param text          正文
        @param context_token 上下文令牌
        @returns (ok, data_or_error)
        """
        ctx = context_token or self.get_context(to_user)
        return self._send_items(to_user,
                                [{"type": proto.ITEM_TEXT, "text_item": {"text": text}}], ctx)

    def send_image(self, to_user, data_url, context_token=""):
        """发送一张图片。

        图片消息项依赖 CDN 预签名上传（getuploadurl + AES 加密），
        属后续迭代范围；当前明确返回不支持，由上层回退为文本说明。
        @returns (ok, data_or_error)
        """
        return False, "image_not_supported_yet"

    # ---------- 长轮询主循环 ----------
    def start(self):
        """启动长轮询后台线程。重复调用幂等。

        @returns 是否成功启动
        """
        if self._running:
            return True
        if not self.load_cred():
            log("无可用凭证，长轮询不启动（需先扫码登录）")
            return False
        self._buf = self._load_buf()
        self._running = True
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """停止长轮询。"""
        self._running = False
        self._ws_connected = False

    def _run_forever(self):
        """长轮询主循环：拉取 → 分发 → 存游标，直到 stop()。"""
        log("长轮询已启动")
        self._ws_connected = True
        while self._running:
            try:
                resp = self.get_updates()
            except Exception as e:
                log("长轮询异常，5 秒后重试：", e)
                self._ws_connected = False
                time.sleep(5)
                continue
            # session 过期：清凭证，等待用户重新扫码
            if self._is_session_expired(resp):
                log("session 已过期，清除凭证待重新扫码")
                self.clear_cred()
                self._ws_connected = False
                self._running = False
                return
            self._ws_connected = True
            self._consume(resp)

    @staticmethod
    def _is_session_expired(resp):
        """判断响应是否为 session 过期。"""
        for key in ("ret", "errcode"):
            try:
                if int(resp.get(key) or 0) == proto.ERRCODE_SESSION_EXPIRED:
                    return True
            except (TypeError, ValueError):
                pass
        return False

    def _consume(self, resp):
        """处理一批响应：先存游标，再逐条分发消息。

        顺序很重要：先存游标再处理消息。若反过来，处理途中崩溃会重放已处理的消息。
        @param resp 长轮询响应
        """
        buf = resp.get("get_updates_buf") or ""
        if buf and buf != self._buf:
            self._buf = buf
            self._save_buf(buf)
        for msg in (resp.get("msgs") or []):
            self._dispatch(msg)

    def _dispatch(self, msg):
        """分发一条消息：记录上下文令牌后交给上层回调。

        @param msg 消息对象
        """
        try:
            sender = msg.get("from_user_id") or ""
            ctx = msg.get("context_token") or ""
            if sender and ctx:
                self.set_context(sender, ctx)
            self._last_event = "message"
            if self.on_message:
                self.on_message(self, msg)
        except Exception as e:
            log("消息分发异常：", e)
