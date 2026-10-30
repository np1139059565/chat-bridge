"""远程桥接 —— 企业微信智能机器人协议基础层

职责：
1. 协议常量（连接地址、命令名、消息类型、超时）
2. 帧构造（cmd + headers.req_id + body）
3. 媒体上传三步（init / chunk / finish）拿 media_id
4. 媒体下载解密（AES-256-CBC，IV 取密钥前 16 字节）

协议事实（对照企业微信官方「智能机器人长连接」文档核实）：
  - 连接地址 wss://openws.work.weixin.qq.com
  - 订阅用 aibot_subscribe，body 带 bot_id 与 secret
  - 回复消息用 aibot_respond_msg，**必须透传回调里的 req_id**，
    另起一个 req_id 会导致回复关联不上原会话
  - 流式回复放在 body.stream（id / index / finish），不是顶层 finish
  - 发送图片/文件：先 aibot_upload_media_init 拿 upload_id 与分片信息，
    再 aibot_upload_media_chunk 逐片上传，最后 aibot_upload_media_finish 拿 media_id
  - 接收侧图片/文件带独立 aeskey，下载后需解密；IV 为密钥前 16 字节
  - 每个机器人同一时刻只允许一条长连接，新连接会踢掉旧连接
  - 心跳间隔 30 秒

设计说明：
  仅依赖标准库 + cryptography（工程已装），不引入新依赖。
  本文件只放「不会随业务变化」的部分，业务编排在 wecom_client。
"""
import base64
import hashlib
import json
import uuid


# ---------- 连接与命令 ----------
WSS_URL = "wss://openws.work.weixin.qq.com"

CMD_SUBSCRIBE = "aibot_subscribe"
CMD_MSG_CALLBACK = "aibot_msg_callback"
CMD_EVENT_CALLBACK = "aibot_event_callback"
CMD_RESPOND_MSG = "aibot_respond_msg"
CMD_RESPOND_WELCOME = "aibot_respond_welcome_msg"
CMD_SEND_MSG = "aibot_send_msg"
CMD_UPLOAD_INIT = "aibot_upload_media_init"
CMD_UPLOAD_CHUNK = "aibot_upload_media_chunk"
CMD_UPLOAD_FINISH = "aibot_upload_media_finish"
CMD_PING = "ping"

# ---------- 超时与重连（秒） ----------
HEARTBEAT_INTERVAL = 30
RECONNECT_DELAY = 5
# 上传分片大小：官方建议 512KB，过大易被网关拒绝，过小则请求次数过多
UPLOAD_CHUNK_SIZE = 512 * 1024

# ---------- 会话类型 ----------
CHAT_SINGLE = 1     # 单聊
CHAT_GROUP = 2      # 群聊


# ---------- 帧构造 ----------
def new_req_id():
    """生成一个新的请求 id。

    @returns 32 位十六进制串
    """
    return uuid.uuid4().hex


def frame(cmd, body=None, req_id=None):
    """构造一帧上行消息。

    @param cmd    命令名
    @param body   消息体字典
    @param req_id 请求 id；为空时自动生成。回复类消息必须传回调带来的 id
    @returns JSON 字符串
    """
    return json.dumps({
        "cmd": cmd,
        "headers": {"req_id": req_id or new_req_id()},
        "body": body or {},
    }, ensure_ascii=False)


def subscribe_frame(bot_id, secret):
    """构造订阅帧。

    @param bot_id 机器人 id
    @param secret 机器人密钥
    @returns JSON 字符串
    """
    return frame(CMD_SUBSCRIBE, {"bot_id": bot_id, "secret": secret})


def respond_frame(req_id, chatid, content, chat_type=CHAT_SINGLE, msgtype="markdown"):
    """构造回复消息帧（一次性发完，非流式分片）。

    关键：req_id 必须用回调带来的那个，新生成的会导致回复关联不上会话。
    消息体里不需要 msg_id——官方格式只用 headers.req_id 关联原消息；
    也不需要分片参数——本工程所有回复都是一次性发完（finish=True）。

    @param req_id    回调带来的请求 id（必须透传）
    @param chatid    会话 id
    @param content   正文
    @param chat_type 1 单聊 / 2 群聊
    @param msgtype   消息类型（markdown / text）
    @returns JSON 字符串
    """
    body = {
        "msgtype": msgtype,
        "chatid": chatid,
        "chat_type": chat_type,
        "stream": {
            "id": new_req_id(),
            "index": 0,
            "finish": True,
        },
    }
    if msgtype == "markdown":
        body["markdown"] = {"content": content}
    else:
        body["text"] = {"content": content}
    return frame(CMD_RESPOND_MSG, body, req_id=req_id)


def respond_image_frame(req_id, chatid, image_b64, image_md5, chat_type=CHAT_SINGLE):
    """构造「回复一张图片」的帧。

    官方格式：图片作为 msg_item 放进 stream 里，在 finish=True 时携带。
    不走传统素材上传接口——那条路需要企业应用的 access_token，
    且受「企业可信IP」白名单限制，本地部署无法满足。

    关键字段（对照官方 SDK 与社区实测）：
      - base64 是原始图片字节的 base64，**不带** data:xxx;base64, 前缀
      - md5 是**原始字节**的 MD5，不是 base64 字符串的 MD5
      - 图片编码前体积上限 10MB，支持 JPG / PNG

    @param req_id     回调带来的请求 id（必须透传）
    @param chatid     会话 id
    @param image_b64  图片的 base64 文本
    @param image_md5  原始图片字节的 md5 十六进制串
    @param chat_type  会话类型
    @param stream_id  流式 id；为空自动生成
    @param caption    附带的文字说明（可为空）
    @returns JSON 字符串
    """
    body = {
        "msgtype": "stream",
        "chatid": chatid,
        "chat_type": chat_type,
        "stream": {
            "id": new_req_id(),
            "finish": True,
            "content": "",
            "msg_item": [{
                "msgtype": "image",
                "image": {"base64": image_b64, "md5": image_md5},
            }],
        },
    }
    return frame(CMD_RESPOND_MSG, body, req_id=req_id)


def send_frame(chatid, chat_type, payload):
    """构造主动推送帧。

    @param chatid    会话 id
    @param chat_type 1 单聊 / 2 群聊
    @param payload   消息体（含 msgtype 与对应内容字段）
    @returns JSON 字符串
    """
    body = {"chatid": chatid, "chat_type": chat_type}
    body.update(payload)
    return frame(CMD_SEND_MSG, body)


# ---------- 媒体上传 ----------
def upload_init_frame(file_name, file_size, media_type="image"):
    """构造媒体上传初始化帧。

    @param file_name  文件名
    @param file_size  文件字节数
    @param media_type image / file / voice / video
    @returns JSON 字符串
    """
    return frame(CMD_UPLOAD_INIT, {
        "file_name": file_name,
        "file_size": int(file_size),
        "media_type": media_type,
    })


def upload_chunk_frame(upload_id, chunk_index, chunk_data_b64):
    """构造媒体分片上传帧。

    @param upload_id      上传会话 id（init 返回）
    @param chunk_index    分片序号，从 0 开始
    @param chunk_data_b64 分片内容的 base64
    @returns JSON 字符串
    """
    return frame(CMD_UPLOAD_CHUNK, {
        "upload_id": upload_id,
        "chunk_index": int(chunk_index),
        "chunk_data": chunk_data_b64,
    })


def upload_finish_frame(upload_id):
    """构造媒体上传完成帧。

    @param upload_id 上传会话 id
    @returns JSON 字符串
    """
    return frame(CMD_UPLOAD_FINISH, {"upload_id": upload_id})


def split_chunks(data, size=UPLOAD_CHUNK_SIZE):
    """把字节串切成若干分片。

    @param data 原始字节
    @param size 分片大小
    @returns 分片列表
    """
    return [data[i:i + size] for i in range(0, len(data), size)]


def b64(data):
    """字节串转 base64 文本。

    @param data 字节
    @returns base64 字符串
    """
    return base64.b64encode(data).decode("ascii")


# ---------- 媒体下载解密 ----------
def decrypt_media(ciphertext, aeskey_b64):
    """解密收到的媒体数据。

    企业微信下发的 aeskey 是 base64 的 32 字节密钥，加密算法为 AES-256-CBC，
    IV 取密钥前 16 字节。密钥长度不足时原样返回，由调用方决定如何降级。

    @param ciphertext 密文字节
    @param aeskey_b64 base64 编码的密钥
    @returns 明文字节
    """
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:
        return ciphertext
    try:
        key = base64.b64decode(aeskey_b64)
    except Exception:
        return ciphertext
    if len(key) < 32:
        return ciphertext
    key = key[:32]
    iv = key[:16]
    try:
        dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        plain = dec.update(ciphertext) + dec.finalize()
        # 去掉 PKCS7 填充
        if plain:
            pad = plain[-1]
            if 1 <= pad <= 16:
                plain = plain[:-pad]
        return plain
    except Exception:
        return ciphertext


def sha256_hex(data):
    """计算 sha256 十六进制摘要，供上传校验使用。

    @param data 字节
    @returns 十六进制串
    """
    return hashlib.sha256(data).hexdigest()
