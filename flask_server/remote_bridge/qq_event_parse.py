"""远程桥接 —— QQ 事件解析与下载辅助

从 qq_gateway.py 抽出，使该文件保持在行数上限内。
本模块只做纯解析与下载，不依赖 QqGateway 实例，便于单独测试。

依赖：bridge_log、paths、标准库
"""
from . import bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][gateway]", *args)


# C2C 单聊消息事件类型
EVENT_C2C_MESSAGE = "C2C_MESSAGE_CREATE"

# 图片扩展名 → MIME 映射（用于拼 dataURL）；未命中默认 image/png
_IMAGE_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp"}


def to_data_url(img_path, ext):
    """把本地图片读成 dataURL 字符串；读取失败返回空串。

    @param img_path 本地图片绝对路径
    @param ext      文件扩展名（用于推断 MIME）
    @returns dataURL；失败空串
    """
    import base64
    try:
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception as e:
        log("读取图片失败：", e)
        return ""
    mime = _IMAGE_MIME.get(ext, "image/png")
    return "data:%s;base64,%s" % (mime, b64)


def extract(d):
    """从事件数据里取出关键字段。

    @return (openid, content, msg_id)；缺字段时对应值为空串
    """
    # 单聊事件的用户标识位于 author.user_openid（群聊场景则为 member_openid）
    author = d.get("author") or {}
    openid = author.get("user_openid") or ""
    content = d.get("content") or ""
    # 消息 id：被动回复要引用它，事件体顶层字段名为 id
    msg_id = d.get("id") or ""
    return openid, str(content).strip(), msg_id


def extract_voice(d):
    """从事件里提取语音附件的音频地址；没有则返回空串。

    容错解析：QQ 语音消息的正文 content 通常为空，音频放在 attachments 里。
    不同版本/场景字段名可能不一致，故多个字段名与判定方式都试一遍：
      - content_type 为 voice / audio；
      - 或 url 以 .silk / .amr 结尾。
    真实的字段结构需用一次真实语音消息校准；此处宁可多试不可漏判。
    """
    atts = d.get("attachments") or []
    for a in atts:
        if not isinstance(a, dict):
            continue
        ct = str(a.get("content_type") or "").lower()
        url = str(a.get("url") or a.get("audio_url") or "")
        if not url:
            continue
        low = url.lower()
        if ct in ("voice", "audio") or low.endswith(".silk") or low.endswith(".amr"):
            return url
    return ""


def extract_image(d):
    """从事件里提取图片附件的下载地址；没有则返回空串。

    容错解析：QQ 图片消息的正文 content 通常为空，图片放在 attachments 里。
    不同版本/场景字段名可能不一致，故多个字段名与判定方式都试一遍：
      - content_type 为 image / pic；
      - 或 url 以常见图片扩展名结尾。
    真实字段结构需用一次真实图片消息校准；此处宁可多试不可漏判。
    """
    atts = d.get("attachments") or []
    for a in atts:
        if not isinstance(a, dict):
            continue
        ct = str(a.get("content_type") or "").lower()
        fname = str(a.get("filename") or "").lower()
        url = str(a.get("url") or a.get("image_url") or "")
        if not url:
            continue
        # content_type 实际形如 image/jpeg、image/png（非裸 "image"），
        # 故用 startswith("image") 判断；再以 filename 扩展名兜底。
        # URL 常为带参数的下载链接、不含扩展名，故不能只看 URL。
        if ct.startswith("image") or ct in ("pic",) \
                or fname.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            return url
    return ""


def download_file(url, dest_path):
    """下载 URL 到本地文件；成功返回 True。

    用标准库 urllib，不引入额外依赖。
    """
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = resp.read()
        with open(dest_path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        log("下载语音文件失败：", e)
        return False


def dump_raw_event(data):
    """把收到的原始 QQ 事件原样追加到调试文件（JSON 行）。

    用途：核对语音消息的真实字段结构（content / attachments / content_type 等）。
    只保留最近 20 条，超过则整体重写，避免文件无限增长。
    正式排查完毕后可移除本调用。
    """
    import os
    import json
    import paths
    dump_path = paths.DATA_DIR / "qq_raw_events.jsonl"
    try:
        os.makedirs(str(paths.DATA_DIR), exist_ok=True)
        # 读取已有行（最多保留 20 条）
        lines = []
        if dump_path.exists():
            lines = dump_path.read_text(encoding="utf-8").splitlines()[-19:]
        lines.append(json.dumps(data, ensure_ascii=False))
        dump_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as e:
        log("落盘原始事件失败：", e)
