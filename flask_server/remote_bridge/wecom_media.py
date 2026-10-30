"""远程桥接 —— 企业微信富媒体（图片 / 文件）

从 wecom_client.py 抽出，使该类保持在行数上限内。

职责：
1. 发送图片 / 文件（走 stream.msg_item 的 base64 + md5，不上传素材）
2. 下载并解密收到的媒体（AES-256-CBC，IV 取密钥前 16 字节）

为什么不用素材上传接口：
  那条路需要企业应用的 access_token，且要求服务器公网 IP 加入
  「企业可信IP」白名单——本地部署无法满足（平台要求先配置可信域名
  或接收消息服务器 URL，而本机没有公网地址）。
  长连接的 msg_item 支持直接带 base64 + md5，绕开这两个限制。

设计：以 Mixin 形式提供方法，由 WecomClient 继承；
依赖宿主类提供 _send_nowait 等基础能力，本模块不重复实现。
"""
import hashlib
import os
import time

import app_log
from . import wecom_proto as proto


# 图片编码前体积上限：平台限制 10MB，超出必然被拒
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def log(*args):
    """统一前缀打印，便于在服务端控制台过滤企业微信日志。"""
    app_log.info("[bridge][wecom]", *args)


class WecomMediaMixin:
    """企业微信富媒体收发能力。"""

    def respond_image(self, req_id, chatid, file_path, chat_type=proto.CHAT_SINGLE,
                      caption=""):
        """回复一张图片（走 msg_item 直传 base64，不上传素材）。

        @param req_id     原消息的请求 id（必须透传，客户端才停止转圈）
        @param chatid     会话 id
        @param file_path  本地图片路径（JPG / PNG，编码前 ≤ 10MB）
        @param chat_type  会话类型
        @param caption    附带文字
        @returns (ok, data_or_error)
        """
        if not req_id or not chatid:
            return False, "missing_req_id_or_chatid"
        try:
            with open(file_path, "rb") as f:
                raw = f.read()
        except Exception as e:
            return False, "read_failed: %s" % e
        if len(raw) > MAX_IMAGE_BYTES:
            return False, "image_too_large"
        b64 = proto.b64(raw)
        md5 = hashlib.md5(raw).hexdigest()
        frame_text = proto.respond_image_frame(req_id, chatid, b64, md5,
                                               chat_type=chat_type, caption=caption)
        ok = self._send_nowait(frame_text)
        return ok, ({} if ok else "send_failed")

    def send_image(self, chatid, file_path, chat_type=proto.CHAT_SINGLE):
        """主动推送一张图片。

        注意：官方主动推送（aibot_send_msg）只支持文本与模板卡片，
        不带 msg_item，故本方法在无 req_id 时无法真正发出图片。
        保留此方法仅为签名兼容，调用方应优先用 respond_image。

        @returns (ok, data_or_error)
        """
        return False, "active_push_no_image_support"

    def send_c2c_image(self, chatid, image_path, msg_id="", msg_seq=1):
        """兼容 QQ 客户端签名的发图入口。"""
        return self.send_image(chatid, image_path)

    def download_media(self, url, aeskey="", dest_dir=""):
        """下载并解密收到的媒体文件。

        @param url      下载地址
        @param aeskey   base64 编码的密钥；为空表示不加密
        @param dest_dir 落盘目录
        @returns 本地路径；失败返回空串
        """
        import urllib.request
        import uuid as _uuid
        if not url:
            return ""
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                raw = resp.read()
        except Exception as e:
            log("下载媒体失败：", e)
            return ""
        data = proto.decrypt_media(raw, aeskey) if aeskey else raw
        try:
            os.makedirs(dest_dir, exist_ok=True)
            ext = os.path.splitext(url.split("?")[0])[1] or ".bin"
            path = os.path.join(dest_dir, "wecom_" + _uuid.uuid4().hex[:12] + ext)
            with open(path, "wb") as f:
                f.write(data)
            return path
        except Exception as e:
            log("媒体落盘失败：", e)
            return ""
