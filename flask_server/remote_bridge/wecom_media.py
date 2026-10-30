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


# 文件头魔数 → 扩展名。各签名无前缀重叠，匹配顺序不影响结果。
# RIFF 容器不在此表：同为 RIFF 前缀的 webp / wav / riff 要靠偏移 8 的类型区分，
# 由 sniff_extension 单独分支处理。
_MAGIC = [
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"BM", ".bmp"),
    (b"%PDF", ".pdf"),
    (b"PK\x03\x04", ".zip"),  # docx/xlsx/pptx 同属 zip
    (b"\x1f\x8b", ".gz"),
    (b"#!AMR", ".amr"),
    (b"OggS", ".ogg"),
    (b"ID3", ".mp3"),
    (b"\xff\xfb", ".mp3"),
    (b"RIFF", ".wav"),       # 需配合偏移 8 的 WAVE
]


def sniff_extension(data):
    """按文件头魔数判断扩展名。

    为什么需要：企业微信的媒体下载地址不带扩展名，
    早先从 URL 取扩展名会永远落到兜底的 .bin，
    导致图片/PDF 保存后前端认不出来、也贴不进输入框。

    @param data 解密后的文件字节
    @returns 带点的扩展名；认不出返回 .bin
    """
    if not data:
        return ".bin"
    head = data[:16]
    # RIFF 容器要再看偏移 8 的类型，区分 webp / wav
    if head[:4] == b"RIFF":
        if head[8:12] == b"WEBP":
            return ".webp"
        if head[8:12] == b"WAVE":
            return ".wav"
        return ".riff"
    for sig, ext in _MAGIC:
        if head.startswith(sig):
            return ext
    # MP4/视频：偏移 4 处是 'ftyp'
    if head[4:8] == b"ftyp":
        return ".mp4"
    return ".bin"


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
        # 走通用媒体帧：旧 respond_image_frame 不接收 caption，
        # 传入会抛 TypeError，故统一改用 respond_media_frame。
        frame_text = proto.respond_media_frame(
            req_id, chatid, proto.image_item(b64, md5),
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

    def _to_amr(self, file_path):
        """把音频转成 AMR 格式；已是 AMR 或转码失败时原样返回。

        为什么要转：平台对语音消息的格式有要求（AMR），而本地 TTS
        合成的是 MP3。不转码直接发，平台会拒收。
        转码用 ffmpeg（工程已依赖它做 WAV→MP3）。

        @param file_path 源音频路径
        @returns (可用路径, 是否临时文件)；转码不可用时原样返回源路径
        """
        if str(file_path).lower().endswith(".amr"):
            return file_path, False
        import subprocess
        import uuid
        out = os.path.join(os.path.dirname(file_path) or ".",
                           "voice_" + uuid.uuid4().hex[:10] + ".amr")
        try:
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", file_path, "-ar", "8000", "-ac", "1",
                 "-c:a", "libopencore_amrnb", "-b:a", "12.2k", out],
                capture_output=True, timeout=60)
            if r.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 0:
                return out, True
            log("语音转 AMR 失败，按原格式发送：", str(r.stderr)[-200:])
        except Exception as e:
            log("语音转 AMR 异常，按原格式发送：", e)
        # 清理可能的半成品
        try:
            if os.path.isfile(out):
                os.remove(out)
        except OSError:
            pass
        return file_path, False

    def respond_voice(self, req_id, chatid, file_path, chat_type=proto.CHAT_SINGLE,
                      caption=""):
        """回复一条语音（走 msg_item 直传 base64，与图片同构）。

        格式限制：平台对语音格式有要求（通常 AMR），调用方须先转好格式。
        转换不在本方法内做——本方法只管把给定文件发出去。

        @param req_id     原消息的请求 id（必须透传）
        @param chatid     会话 id
        @param file_path  本地音频路径
        @param chat_type  会话类型
        @param caption    附带文字
        @returns (ok, data_or_error)
        """
        if not req_id or not chatid:
            return False, "missing_req_id_or_chatid"
        # 平台要求 AMR：先转码，发完再清理临时文件
        use_path, is_tmp = self._to_amr(file_path)
        try:
            try:
                with open(use_path, "rb") as f:
                    raw = f.read()
            except Exception as e:
                return False, "read_failed: %s" % e
            if not raw:
                return False, "empty_file"
            b64 = proto.b64(raw)
            md5 = hashlib.md5(raw).hexdigest()
            frame_text = proto.respond_media_frame(
                req_id, chatid, proto.voice_item(b64, md5),
                chat_type=chat_type, caption=caption)
            ok = self._send_nowait(frame_text)
            return ok, ({} if ok else "send_failed")
        finally:
            # 转码产物是用完即弃的临时文件，无论成败都删掉
            if is_tmp:
                try:
                    os.remove(use_path)
                except OSError:
                    pass

    def _upload_media(self, file_path, media_type="file"):
        """三步上传取 media_id：初始化 → 逐片上传 → 完成。

        大文件不能塞进单帧，必须走这条路。每步都要等平台应答，
        用客户端已有的 _send_wait（按 req_id 配对）实现同步等待。

        @param file_path  本地文件路径
        @param media_type 平台媒体类型：file / image / voice / video
        @returns (media_id, error)
        """
        try:
            with open(file_path, "rb") as f:
                raw = f.read()
        except Exception as e:
            return "", "read_failed: %s" % e
        if not raw:
            return "", "empty_file"
        name = os.path.basename(file_path)

        # 第一步：初始化，拿 upload_id
        rid = proto.new_req_id()
        ack = self._send_wait(
            proto.frame(proto.CMD_UPLOAD_INIT,
                        {"file_name": name, "file_size": len(raw),
                         "media_type": media_type}, req_id=rid), rid)
        if not ack:
            return "", "upload_init_timeout"
        if ack.get("errcode") not in (0, None):
            return "", "upload_init_failed: %s" % ack.get("errmsg")
        upload_id = (ack.get("body") or {}).get("upload_id") or ack.get("upload_id") or ""
        if not upload_id:
            return "", "no_upload_id"

        # 第二步：逐片上传
        for idx, chunk in enumerate(proto.split_chunks(raw)):
            rid = proto.new_req_id()
            ack = self._send_wait(
                proto.frame(proto.CMD_UPLOAD_CHUNK,
                            {"upload_id": upload_id, "chunk_index": idx,
                             "chunk_data": proto.b64(chunk)}, req_id=rid), rid)
            if not ack:
                return "", "upload_chunk_timeout@%d" % idx
            if ack.get("errcode") not in (0, None):
                return "", "upload_chunk_failed@%d: %s" % (idx, ack.get("errmsg"))

        # 第三步：完成，拿 media_id
        rid = proto.new_req_id()
        ack = self._send_wait(
            proto.frame(proto.CMD_UPLOAD_FINISH, {"upload_id": upload_id}, req_id=rid), rid)
        if not ack:
            return "", "upload_finish_timeout"
        if ack.get("errcode") not in (0, None):
            return "", "upload_finish_failed: %s" % ack.get("errmsg")
        body = ack.get("body") or ack
        media_id = body.get("media_id") or ""
        return (media_id, "") if media_id else ("", "no_media_id")

    def respond_file(self, req_id, chatid, file_path, chat_type=proto.CHAT_SINGLE,
                     caption=""):
        """回复一个文件：先三步上传拿 media_id，再发文件消息项。

        @param req_id     原消息的请求 id（必须透传）
        @param chatid     会话 id
        @param file_path  本地文件路径
        @param chat_type  会话类型
        @param caption    附带文字
        @returns (ok, data_or_error)
        """
        if not req_id or not chatid:
            return False, "missing_req_id_or_chatid"
        media_id, err = self._upload_media(file_path, "file")
        if err:
            return False, err
        frame_text = proto.respond_media_frame(
            req_id, chatid, proto.file_item(media_id, os.path.basename(file_path)),
            chat_type=chat_type, caption=caption)
        ok = self._send_nowait(frame_text)
        return ok, ({} if ok else "send_failed")

    def send_c2c_file(self, chatid, file_path, msg_id="", msg_seq=1):
        """兼容 QQ 客户端签名的发文件入口。

        企业微信的主动推送不支持 msg_item，无 req_id 时发不了文件；
        此处如实返回失败原因，不做假装成功。

        @returns (ok, data_or_error)
        """
        return False, "active_push_no_file_support"

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
            # 扩展名必须从文件头魔数判断：企业微信的媒体地址不带扩展名，
            # 从 URL 取会永远落到兜底的 .bin，前端无法识别成图片/PDF。
            ext = sniff_extension(data)
            path = os.path.join(dest_dir, "wecom_" + _uuid.uuid4().hex[:12] + ext)
            with open(path, "wb") as f:
                f.write(data)
            return path
        except Exception as e:
            log("媒体落盘失败：", e)
            return ""
