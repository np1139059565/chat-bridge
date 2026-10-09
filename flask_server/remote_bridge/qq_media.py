"""远程桥接 —— QQ 富媒体（图片 / 语音）发送

从 qq_client.py 抽出，使该类保持在行数上限内。

职责：把本地文件（图片 / 语音）上传为 QQ 富媒体并发送到单聊。
链路：本地文件 → Base64 → 上传拿 file_info → 发 msg_type=7。

设计：
- 以 Mixin 形式提供方法，由 QQClient 继承；
- 依赖宿主类（QQClient）提供 _http_post / _auth_header / _ensure_token /
  _http_error_detail 等基础能力，本模块不重复实现。
"""
import base64
import urllib.error
import app_log


def log(*args):
    """统一前缀打印。"""
    app_log.info("[bridge][qq]", *args)


def _api_base():
    """延迟取 QQ 接口域名，避免与 qq_client 循环导入。"""
    from .qq_client import API_BASE
    return API_BASE


class QqMediaMixin:
    """QQ 富媒体发送能力：图片与语音共用一套「上传 + 发送」流程。"""

    @staticmethod
    def _read_file_b64(path):
        """读取本地文件并 Base64 编码为 ASCII 字符串；失败由调用方捕获。"""
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")

    def _upload_image(self, openid, b64):
        """上传图片富媒体，返回 (file_info, error)。

        上传接口支持 url 与 file_data 二选一；用 file_data 传本地内容，
        就绕开了「QQ 服务器来取图」对公网地址的依赖。
        file_type=1 表示图片；srv_send_msg=False 表示只返回 file_info、不自动发送。
        """
        url = _api_base() + "/v2/users/%s/files" % openid
        try:
            up = self._http_post(url, {
                "file_type": 1,
                "file_data": b64,
                "srv_send_msg": False,
            }, self._auth_header())
        except urllib.error.HTTPError as e:
            return "", "upload HTTP %s %s" % (e.code, self._http_error_detail(e))
        except Exception as e:
            return "", str(e)
        return (up or {}).get("file_info") or "", ""

    def _upload_voice(self, openid, b64):
        """上传语音富媒体，返回 (file_info, error)。

        与图片上传同路，差别在 file_type：图片=1，语音=3。
        用 file_data 传本地内容，绕开「QQ 服务器来取文件」对公网地址的依赖。
        srv_send_msg=False 表示只返回 file_info、不自动发送。
        """
        url = _api_base() + "/v2/users/%s/files" % openid
        try:
            up = self._http_post(url, {
                "file_type": 3,          # 3 = 语音
                "file_data": b64,
                "srv_send_msg": False,
            }, self._auth_header())
        except urllib.error.HTTPError as e:
            return "", "upload HTTP %s %s" % (e.code, self._http_error_detail(e))
        except Exception as e:
            return "", str(e)
        return (up or {}).get("file_info") or "", ""

    def _send_media(self, openid, file_info, msg_id, msg_seq):
        """发送富媒体消息（msg_type=7），返回 (ok, data_or_error)。"""
        url = _api_base() + "/v2/users/%s/messages" % openid
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
            return False, "send HTTP %s %s" % (e.code, self._http_error_detail(e))
        except Exception as e:
            return False, str(e)

    def send_c2c_image(self, openid, image_path, msg_id="", msg_seq=1):
        """发送单聊图片（富媒体）。

        用本地文件直接上传，无需公网地址：
        读文件 → Base64 编码 → 作为 file_data 上传拿 file_info → 发 msg_type=7。
        上传接口路径、file_type 取值、msg_type=7 的消息体结构已核对官方文档。
        @param openid     接收方用户 openid
        @param image_path 本地图片文件路径
        @param msg_id     被动回复引用的用户消息 id
        @param msg_seq    同一 msg_id 下的序号
        @returns (ok, data_or_error)
        """
        if not self._ensure_token():
            return False, "no_token"
        try:
            b64 = self._read_file_b64(image_path)
        except Exception as e:
            return False, "read_file_failed: %s" % e
        # 第一步：上传富媒体，拿 file_info
        file_info, err = self._upload_image(openid, b64)
        if err:
            return False, err
        if not file_info:
            return False, "no_file_info"
        # 第二步：发送富媒体消息
        return self._send_media(openid, file_info, msg_id, msg_seq)

    def send_c2c_voice(self, openid, voice_path, msg_id="", msg_seq=1):
        """发送单聊语音（富媒体）。

        读本地音频文件 → Base64 编码 → 作为 file_data 上传（file_type=3）
        拿 file_info → 发 msg_type=7。
        注意：QQ 语音富媒体对格式有要求，MP3 是否被接受需实测；
        若平台只收 SILK，则需在调用侧先把音频转成 SILK 再传入。
        @param openid     接收方用户 openid
        @param voice_path 本地音频文件路径
        @param msg_id     被动回复引用的用户消息 id
        @param msg_seq    同一 msg_id 下的序号
        @returns (ok, data_or_error)
        """
        if not self._ensure_token():
            return False, "no_token"
        try:
            b64 = self._read_file_b64(voice_path)
        except Exception as e:
            return False, "read_file_failed: %s" % e
        # 第一步：上传语音富媒体，拿 file_info
        file_info, err = self._upload_voice(openid, b64)
        if err:
            return False, err
        if not file_info:
            return False, "no_file_info"
        # 第二步：发送富媒体消息
        return self._send_media(openid, file_info, msg_id, msg_seq)
