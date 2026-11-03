"""远程桥接 —— 企业微信出站媒体收集

从 wecom_router.py 抽出，使该文件保持在行数上限内。

职责：把一条消息里的图片 / 文件 / 语音落成本地文件，供发送层取用。
发送本身不在这里（见 wecom_media.WecomMediaMixin）。

三类媒体的差异：
  图片 —— dataURL 或 http 地址，落盘后由 respond_image 直传 base64；
  文件 —— 本地路径或 http 地址，落盘后由 respond_file 走三步上传；
  语音 —— 由上游 TTS 预先合成好，这里只做定位与存在性校验。
"""
import base64
import os
import urllib.request
import uuid
from urllib.parse import unquote

import paths
from . import bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][wecom]", *args)


# 图片落盘时可识别的扩展名（按优先级）
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def collect_images(m):
    """取出消息里的图片块（dataURL 或 http 地址），落盘后返回路径列表。

    @param m 消息对象
    @returns 本地路径列表
    """
    out = []
    for b in (m.get("blocks") or []):
        if not b or b.get("type") != "image":
            continue
        src = str(b.get("src") or "")
        if not src:
            continue
        # 相对接口地址先按前缀直接定位本地文件；命中就不必再走网络下载
        path = resolve_local_image(src) or materialize_image(src)
        if path:
            out.append(path)
    return out


def collect_files(m):
    """取出消息里的文件块（本地路径，或可下载的 http 地址）。

    与图片的区别：文件发出去靠「三步上传拿 media_id」而非 base64 直传，
    故这里只需给出本地路径，上传细节交给 respond_file。
    文件块里常见的字段是 path / url 与 name，两者都兼容。
    @param m 消息对象
    @returns 本地路径列表
    """
    out = []
    # 文件信息的真实落点是消息的 files 字段：块类型里没有「文件」这一种，
    # 附件以独立字段挂在消息上（见前端建节点处）。只扫 blocks 会一条都取不到。
    for f in (m.get("files") or []):
        if not isinstance(f, dict):
            continue
        # 优先用本地路径；没有就把 http 地址下载下来
        path = str(f.get("path") or "")
        if not path:
            src = str(f.get("url") or f.get("src") or "")
            if src.startswith(("http://", "https://")):
                path = download_to_media(src, str(f.get("name") or ""))
        if path and os.path.isfile(path):
            out.append(path)
    # 兼容旧格式：块里直接带文件路径的历史消息
    for b in (m.get("blocks") or []):
        if not b or b.get("type") != "file":
            continue
        path = str(b.get("path") or "")
        if not path:
            src = str(b.get("src") or b.get("url") or "")
            if src.startswith(("http://", "https://")):
                path = download_to_media(src, str(b.get("name") or ""))
        if path and os.path.isfile(path) and path not in out:
            out.append(path)
    return out


def collect_voice(m, voice_paths=None):
    """取出消息里要推送的语音文件。

    语音不进正文：正文已有文字，语音是附加形态。与 QQ 通道一致，
    只在 AI 消息上推语音，且合成失败的条目会被上游跳过。

    音频来源优先取 voice_paths（调用方在锁外预合成好的），
    其次取消息自带的 voice 字段（网页播放器已生成过音频）。

    @param m           消息对象
    @param voice_paths 预合成结果 {消息id: 音频路径}
    @returns (本地音频路径, 朗读文本) 二元组；无语音返回 ("", "")
    """
    # 延迟导入：复用远程桥接既有的语音块提取规则，避免两处判定不一致
    try:
        from .message_voice import extract_voice_from_blocks
        text = extract_voice_from_blocks(m) or ""
    except Exception:
        text = ""
    if not text:
        return "", ""
    # 优先取锁外预合成好的音频：那是本轮真正生成的 TTS 产物，
    # 放在 voice_paths 里按消息 id 索引。此前该参数被收下却从未使用，
    # 导致语音永远取不到路径、一条都发不出去。
    mid = str(m.get("id") or "")
    path = str((voice_paths or {}).get(mid) or "") or str(m.get("voice") or "")
    if not path:
        return "", text
    # voice 字段可能只是文件名，统一解析到网页音频目录
    if not os.path.isabs(path):
        path = str(paths.WEB_AUDIO_DIR / path)
    return (path if os.path.isfile(path) else ""), text


def download_to_media(src, name=""):
    """把 http 地址下载到媒体目录，返回本地路径；失败返回空串。

    @param src  下载地址
    @param name 原始文件名（用于保留扩展名）
    @returns 本地路径
    """
    try:
        os.makedirs(str(paths.WECOM_MEDIA_DIR), exist_ok=True)
        ext = os.path.splitext(name or src.split("?")[0])[1] or ".bin"
        path = str(paths.WECOM_MEDIA_DIR / ("out_" + uuid.uuid4().hex[:12] + ext))
        with urllib.request.urlopen(src, timeout=60) as r, open(path, "wb") as f:
            f.write(r.read())
        return path
    except Exception as e:
        log("文件下载失败：", e)
        return ""


# 接口路径前缀 → 本地目录：前端上报的图片地址常是相对接口地址，
# 直接按前缀映射到磁盘目录取文件，比再发一次 HTTP 请求稳且快。
_LOCAL_IMAGE_ROUTES = (
    ("/api/web/image-file/", lambda: paths.WEB_IMAGES_DIR),
    ("/api/web/screenshot-file/", lambda: paths.SCREENSHOTS_DIR),
)


def resolve_local_image(src):
    """把相对接口地址解析成本地图片文件路径。

    前端采集图片时 src 可能是 `/api/web/image-file/xxx.png` 这样的相对地址，
    而非 dataURL 或 http 绝对地址。这类地址不解析就会被当成无效源丢弃，
    表现为「图片一条都发不出去」。

    @param src 图片地址
    @returns 本地路径；无法解析或文件不存在返回空串
    """
    if not src.startswith("/"):
        return ""
    for prefix, dir_fn in _LOCAL_IMAGE_ROUTES:
        if not src.startswith(prefix):
            continue
        name = src[len(prefix):].split("?")[0]
        # 只接受纯文件名：带路径分隔符一律拒绝，避免越权读到目录外
        if not name or "/" in name or "\\" in name or ".." in name:
            return ""
        try:
            path = str(dir_fn() / unquote(name))
        except Exception:
            return ""
        return path if os.path.isfile(path) else ""
    return ""


def materialize_image(src):
    """把图片地址落成本地文件，返回路径；失败返回空串。

    @param src dataURL 或 http(s) 地址
    @returns 本地路径
    """
    try:
        os.makedirs(str(paths.WECOM_MEDIA_DIR), exist_ok=True)
    except OSError:
        return ""
    name = "out_" + uuid.uuid4().hex[:12]
    # dataURL：解码后直接写盘，扩展名从 MIME 头推断
    if src.startswith("data:image/"):
        try:
            head, _, b64part = src.partition(",")
            ext = ".png"
            if "jpeg" in head or "jpg" in head:
                ext = ".jpg"
            elif "gif" in head:
                ext = ".gif"
            elif "webp" in head:
                ext = ".webp"
            data = base64.b64decode(b64part)
            path = str(paths.WECOM_MEDIA_DIR / (name + ext))
            with open(path, "wb") as f:
                f.write(data)
            return path
        except Exception as e:
            log("dataURL 落盘失败：", e)
            return ""
    # http(s)：下载落盘，扩展名优先取 URL 末段
    if src.startswith(("http://", "https://")):
        try:
            ext = ".png"
            low = src.lower().split("?")[0]
            for e in _IMAGE_EXTS:
                if low.endswith(e):
                    ext = e
                    break
            path = str(paths.WECOM_MEDIA_DIR / (name + ext))
            with urllib.request.urlopen(src, timeout=30) as r, open(path, "wb") as f:
                f.write(r.read())
            return path
        except Exception as e:
            log("图片下载失败：", e)
            return ""
    return ""
