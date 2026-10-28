"""远程桥接 —— 微信 iLink 协议基础层

职责：
1. 协议常量（接口地址、应用标识、消息项类型、状态码）
2. 版本号编码、请求头构造、请求体基础结构
3. 一个薄 HTTP 客户端，供上层 WeixinClient 复用

为什么单独成文件：
  协议常量与 HTTP 细节属「不会随业务逻辑变化」的部分，
  与 WeixinClient 的登录、长轮询、发送等业务逻辑分离后，
  两边各自可读，也避免单文件超出长度上限。

协议事实（对照官方插件 @tencent-weixin/openclaw-weixin 2.4.10 源码核实）：
  - 接口基地址 https://ilinkai.weixin.qq.com（登录后可能被地域跳转改写）
  - 请求头 iLink-App-Id 固定为 "bot"
  - iLink-App-ClientVersion 是包版本三段的位运算编码
  - X-WECHAT-UIN 是「随机 uint32 → 十进制字符串 → base64」
  - 每个请求体都带 base_info：{channel_version, bot_agent}
"""
import base64
import json
import random
import urllib.error
import urllib.parse
import urllib.request


# ---------- 接口地址 ----------
DEFAULT_BASE = "https://ilinkai.weixin.qq.com"

# ---------- 协议常量（对照官方插件源码核实） ----------
# 应用标识：官方 package.json 顶层 ilink_appid 字段的值。
ILINK_APP_ID = "bot"
# 渠道版本：官方取插件 package.json 的 version。
CHANNEL_VERSION = "2.4.10"
# 机器人代理标识：协议要求形如 UA，缺省值为 OpenClaw。
BOT_AGENT = "OpenClaw"
# 二维码对应的 bot_type，当前通道构建固定为 3。
DEFAULT_BOT_TYPE = "3"

# ---------- 超时（秒），与官方一致 ----------
LONG_POLL_TIMEOUT = 35
API_TIMEOUT = 15
QR_POLL_TIMEOUT = 35

# ---------- 错误码 ----------
# session 过期，遇到即清凭证重新扫码。
ERRCODE_SESSION_EXPIRED = -14

# ---------- 消息项类型（对照官方 types.js） ----------
ITEM_TEXT = 1
ITEM_IMAGE = 2
ITEM_VOICE = 3
ITEM_FILE = 4
ITEM_VIDEO = 5

# ---------- 消息类型与状态 ----------
MSG_TYPE_BOT = 2
MSG_STATE_FINISH = 2

# ---------- 媒体上传类型（getuploadurl 用） ----------
UPLOAD_IMAGE = 1
UPLOAD_VIDEO = 2
UPLOAD_FILE = 3
UPLOAD_VOICE = 4


# ---------- 编码与请求构造 ----------
def build_client_version(version):
    """把三段版本号编码成 uint32：高 8 位固定 0，其余 major<<16 | minor<<8 | patch。

    与官方 buildClientVersion 完全一致，例如 2.4.10 → 0x0204000A。
    @param version 形如 "2.4.10" 的版本字符串
    @returns 编码后的整数
    """
    parts = []
    for p in str(version or "0.0.0").split("."):
        try:
            parts.append(int(p))
        except (TypeError, ValueError):
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    major, minor, patch = parts[0], parts[1], parts[2]
    return ((major & 0xFF) << 16) | ((minor & 0xFF) << 8) | (patch & 0xFF)


# 客户端版本整数：随渠道版本一起推导，避免两处各写一个魔数。
ILINK_APP_CLIENT_VERSION = build_client_version(CHANNEL_VERSION)


def random_wechat_uin():
    """生成 X-WECHAT-UIN 请求头。

    官方实现是「随机 uint32 → 十进制字符串 → base64」，
    不是把二进制直接打包，两者产出的头部值不同，必须按官方来。
    @returns base64 编码的头部值
    """
    n = random.getrandbits(32)
    return base64.b64encode(str(n).encode("utf-8")).decode("ascii")


def base_info():
    """构造每个请求体都要带的版本信息结构。

    @returns {channel_version, bot_agent}
    """
    return {"channel_version": CHANNEL_VERSION, "bot_agent": BOT_AGENT}


def build_headers(token=""):
    """构造请求头。

    与官方 buildHeaders 对齐：固定头 + 可选的 Bearer 令牌。
    @param token 机器人令牌；为空时不带 Authorization
    @returns 请求头字典
    """
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": random_wechat_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def join_url(base, path):
    """拼接完整接口地址，自动处理基地址末尾斜杠。

    @param base 基地址；为空时用默认地址
    @param path 接口路径，如 ilink/bot/getupdates
    @returns 完整 URL
    """
    b = base or DEFAULT_BASE
    if not b.endswith("/"):
        b += "/"
    return urllib.parse.urljoin(b, path)


# ---------- HTTP ----------
def request(url, body=None, token="", method="POST", timeout=API_TIMEOUT):
    """发一个 HTTP 请求并解析 JSON；失败抛异常。

    @param url     完整地址
    @param body    请求体字典；GET 时忽略
    @param token   令牌
    @param method  POST / GET
    @param timeout 超时秒数
    @returns 解析后的字典
    """
    data = None
    if method == "POST":
        data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in build_headers(token).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def read_http_error(e):
    """读取 HTTPError 的响应体，失败时返回空串。

    诊断信息缺失不应盖过「请求失败」这个主结果。
    @param e HTTPError 异常
    @returns 响应体文本（截断）
    """
    try:
        return e.read().decode("utf-8")[:300]
    except Exception:
        return ""
