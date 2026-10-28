"""远程桥接 —— 微信扫码登录状态机

职责：把 iLink 的扫码登录流程封装成「页面可轮询的状态机」。

为什么需要状态机：
  扫码登录天然是异步的——页面点一下「登录」，拿到二维码，
  用户用手机扫，可能等十几秒、可能要先输验证码、可能二维码过期。
  这些状态必须能被页面反复查询，而不是让一个 HTTP 请求干等五分钟。

状态流转：
  idle → waiting（已出二维码）→ scanned（已扫待确认）
       → need_verify（需输手机上的数字）→ confirmed（登录成功）
  异常分支：expired（过期，自动刷新，超次数则失败）、blocked（多次输错）

线程模型：
  轮询在后台线程跑，状态存内存。页面每 2 秒查一次状态即可。
  同一时刻只允许一个登录流程，避免多个二维码互相覆盖。
"""
import threading
import time

from . import bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][weixin]", *args)


# 二维码有效期（秒）：官方为 5 分钟，这里留出余量。
QR_TTL = 5 * 60
# 轮询间隔（秒）：状态查询本身是长轮询，失败后短暂等待再试。
POLL_INTERVAL = 1


class WeixinLogin:
    """扫码登录状态机：持有当前登录会话的全部状态。"""

    def __init__(self, client):
        """
        @param client WeixinClient 实例（登录成功后把凭证写进去）
        """
        self.client = client
        self._lock = threading.RLock()
        self._thread = None
        self._state = "idle"      # 当前状态
        self._qrcode = ""         # 二维码标识
        self._qr_url = ""         # 二维码内容（供前端渲染成图）
        self._message = ""        # 给用户看的说明文字
        self._started = 0         # 本次登录开始时间
        self._base = ""           # 当前轮询基地址（可能被地域跳转改写）
        self._verify_code = ""    # 待提交的验证码
        self._refresh_count = 0   # 已刷新二维码次数

    # ---------- 状态读取 ----------
    def status(self):
        """返回当前登录状态，供页面轮询展示。

        @returns {state, qrcode_url, message, connected}
        """
        with self._lock:
            return {
                "state": self._state,
                "qrcode_url": self._qr_url,
                "message": self._message,
                "connected": self.client.has_cred(),
                # 需要输验证码时，前端据此弹出输入框
                "need_verify": self._state == "need_verify",
            }

    def _set(self, state, message="", qr_url=None, qrcode=None):
        """更新状态字段。

        @param state   新状态
        @param message 给用户看的说明
        @param qr_url  二维码内容；None 表示保持不变
        @param qrcode  二维码标识；None 表示保持不变
        """
        with self._lock:
            self._state = state
            self._message = message
            if qr_url is not None:
                self._qr_url = qr_url
            if qrcode is not None:
                self._qrcode = qrcode

    # ---------- 启动与取消 ----------
    def start(self, base=""):
        """发起一次登录：取二维码并在后台开始轮询。

        已有进行中的登录时直接返回当前状态，避免重复取码。
        @param base 基地址；为空用默认地址
        @returns 当前状态字典
        """
        with self._lock:
            if self._state in ("waiting", "scanned", "need_verify"):
                return self.status()
            self._state = "waiting"
            self._message = "正在获取二维码…"
            self._qr_url = ""
            self._qrcode = ""
            self._verify_code = ""
            self._refresh_count = 0
            self._started = time.time()
            self._base = base or ""
        if self._thread and self._thread.is_alive():
            return self.status()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self.status()

    def submit_verify(self, code):
        """提交手机显示的验证码，供下一轮轮询使用。

        @param code 验证码
        @returns 是否已受理
        """
        with self._lock:
            if self._state != "need_verify":
                return False
            self._verify_code = str(code or "").strip()
            self._state = "waiting"
            self._message = "正在校验验证码…"
            return True

    def cancel(self):
        """取消本次登录。"""
        with self._lock:
            self._state = "idle"
            self._message = "已取消"

    # ---------- 主流程 ----------
    def _run(self):
        """登录主流程：取码 → 轮询 → 成功写凭证。"""
        try:
            self._fetch_qr()
        except Exception as e:
            log("获取二维码失败：", e)
            self._set("failed", "获取二维码失败：%s" % str(e)[:120])
            return
        deadline = time.time() + QR_TTL + 60
        while time.time() < deadline:
            with self._lock:
                # 被用户取消即退出
                if self._state == "idle":
                    return
                qrcode = self._qrcode
                base = self._base
                code = self._verify_code
            if not qrcode:
                time.sleep(POLL_INTERVAL)
                continue
            st = self.client.poll_qrcode_status(qrcode, base or "", code)
            if self._handle_status(st):
                return
            time.sleep(POLL_INTERVAL)
        self._set("failed", "登录超时，请重新发起")

    def _fetch_qr(self):
        """取一张二维码并更新状态。"""
        from .weixin_proto import DEFAULT_BASE
        base = self._base or DEFAULT_BASE
        qr = self.client.fetch_qrcode(base)
        qrcode = qr.get("qrcode") or ""
        url = qr.get("qrcode_img_content") or ""
        if not qrcode:
            raise RuntimeError("服务端未返回二维码标识")
        self._set("waiting", "请用手机微信扫描二维码", qr_url=url, qrcode=qrcode)
        log("二维码已获取")

    def _handle_status(self, st):
        """处理一次扫码状态查询结果。

        @param st 状态字典
        @returns 流程是否结束（成功或彻底失败）
        """
        status = st.get("status") or "wait"
        if status == "wait":
            return False
        if status == "scaned":
            self._set("scanned", "已扫描，请在手机上确认")
            with self._lock:
                self._verify_code = ""
            return False
        if status == "need_verifycode":
            self._set("need_verify", "请输入手机微信上显示的数字")
            return False
        if status == "scaned_but_redirect":
            host = st.get("redirect_host") or ""
            if host:
                with self._lock:
                    self._base = "https://" + host
                log("已切换到地域节点：", host)
            return False
        if status == "expired":
            return self._on_expired()
        if status == "verify_code_blocked":
            self._set("failed", "验证码多次输错，请稍后重试")
            return True
        if status == "binded_redirect":
            self._set("confirmed", "该微信已绑定过此服务，无需重复连接")
            return True
        if status == "confirmed":
            return self._on_confirmed(st)
        return False

    def _on_expired(self):
        """二维码过期：未超次数则刷新，否则失败。

        @returns 流程是否结束
        """
        with self._lock:
            self._refresh_count += 1
            n = self._refresh_count
        if n > 3:
            self._set("failed", "二维码多次过期，请重新发起登录")
            return True
        log("二维码已过期，正在刷新（%d/3）" % n)
        try:
            self._fetch_qr()
        except Exception as e:
            self._set("failed", "刷新二维码失败：%s" % str(e)[:120])
            return True
        return False

    def _on_confirmed(self, st):
        """登录成功：把凭证写入客户端。

        @param st 状态字典（含 bot_token / ilink_bot_id / baseurl / ilink_user_id）
        @returns 恒为 True（流程结束）
        """
        token = st.get("bot_token") or ""
        bot_id = st.get("ilink_bot_id") or ""
        if not token or not bot_id:
            self._set("failed", "登录失败：服务端未返回完整凭证")
            return True
        cred = {
            "token": token,
            "bot_id": bot_id,
            "base_url": st.get("baseurl") or "",
            "user_id": st.get("ilink_user_id") or "",
            "saved_at": int(time.time()),
        }
        self.client.save_cred(cred)
        self._set("confirmed", "登录成功")
        log("登录成功 bot_id=" + bot_id[:8])
        return True
