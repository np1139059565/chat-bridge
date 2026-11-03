"""远程桥接 —— 卡片投递公共层

职责：把「用户发来的内容」投成卡片，交给抽屉渲染。

为什么要有公共层：
    各网关原先各写一份 _deliver_as_card / _deliver_image_card，
    逻辑几乎相同，差异只有三处：来源标记（source）、标题文案、
    是否附带同消息文字。重复实现的代价已经真实发生：
    企业微信版漏了多图支持，一条四图消息被拆成四张独立卡片，
    前端逐张贴图，顺序与归属全部错乱。

    本模块把这些能力收拢到一处，各通道只传「我是谁、叫什么名」，
    不再各自拼卡片。通道能力不足时（如微信不支持图片），
    由调用方决定降级方式，公共层不替它做主。

卡片类型沿用既有的 qq-image / qq-file / external-call：
抽屉早已按这些类型消费，沿用可避免前端同步改动。
"""
import os

import card_bus
from .. import bridge_log


# 图片扩展名 → MIME，用于拼 dataURL；未命中按 png 处理
_IMAGE_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp",
               ".bmp": "image/bmp"}


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][delivery]", *args)


def to_data_url(img_path):
    """把本地图片读成 dataURL 字符串；读取失败返回空串。

    @param img_path 本地图片绝对路径
    @returns dataURL；失败空串
    """
    import base64
    try:
        with open(img_path, "rb") as f:
            raw = f.read()
    except Exception as e:
        log("读取图片失败：", e)
        return ""
    if not raw:
        return ""
    # 按扩展名推 MIME；未知扩展名按 png，平台能自行识别内容
    ext = os.path.splitext(img_path)[1].lower()
    mime = _IMAGE_MIME.get(ext, "image/png")
    return "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode("ascii"))


def deliver_images(source, openid, sources=None, text="", title=None, extra=None):
    """把一组图片投成**一张**卡片，可附带同消息文字。

    多图必须合并且只投一张：拆成多张会让前端逐张贴图，
    既丢失「同一条消息」的归属，也打乱贴图顺序。

    两种输入形态，按来源选其一：
      - paths：本地文件路径，本函数负责转 dataURL（QQ / 企微走这条）；
      - data_urls：已是 dataURL 的数组（网页版上传后直接拿到，无需转码）。

    @param source    通道标识（qq / wecom / web）
    @param openid    接收方标识
    @param paths     本地图片路径列表
    @param text      随图附带的文字；为空时补「用户截图」给模型上下文
    @param title     卡片标题；缺省按通道名生成
    @param data_urls 已转好的 dataURL 列表（与 paths 二选一）
    @param extra     附加到 payload 的字段（如网页版的 image_names）
    @returns 卡片 id；无可用图片时返回空串
    """
    # 逐个识别来源形态：data: 开头是已转好的 dataURL，其余按本地路径读取。
    # 这样调用方不必区分两种参数名，一条通道传自己的那种即可。
    urls = []
    used = []
    for s in (sources or []):
        s = str(s or "")
        if not s:
            continue
        if s.startswith("data:"):
            urls.append(s)
            continue
        u = to_data_url(s)
        if u:
            urls.append(u)
            used.append(s)
    if not urls:
        log("图片全部转码失败，跳过投递")
        return ""
    payload = {
        "kind": "qq-image",
        # data_urls：前端优先读数组，一次贴多张
        "data_urls": urls,
        # data_url：单张兼容字段，旧消费端只认它时取第一张
        "data_url": urls[0],
        "openid": openid,
        "path": used[0] if used else "",
        "text": (text or "").strip() or "用户截图",
    }
    if extra:
        payload.update(extra)
    try:
        card = card_bus.bus.create(
            source=source,
            card_type="qq-image",
            title=title or (source + " 图片"),
            content="（图片，自动贴入网页 AI 输入框）",
            payload=payload,
        )
        log("已投递图片卡片", card.id[:8], "张数=%d" % len(urls))
        return card.id
    except Exception as e:
        log("投递图片卡片失败：", e)
        return ""


def deliver_file(source, openid, path, name="", title=None):
    """把一个本地文件投成卡片，卡片正文写明路径与体积。

    文件是二进制，模型看不见也不需要看见，它需要的是路径。

    @param source 通道标识
    @param openid 接收方标识
    @param path   本地文件路径
    @param name   展示用文件名；缺省取基本名
    @param title  卡片标题；缺省按通道名生成
    @returns 卡片 id；失败返回空串
    """
    name = name or os.path.basename(path)
    size = os.path.getsize(path) if os.path.exists(path) else 0
    body = "用户从%s发来文件：%s（%d 字节），已保存到 %s" % (source, name, size, path)
    try:
        card = card_bus.bus.create(
            source=source,
            card_type="qq-file",
            title=title or (source + " 文件"),
            content=body,
            payload={"kind": "qq-file", "openid": openid,
                     "path": path, "name": name, "size": size},
        )
        log("已投递文件卡片", card.id[:8], "name=" + name)
        return card.id
    except Exception as e:
        log("投递文件卡片失败：", e)
        return ""


def deliver_text(source, openid, text, title=None, extra=None):
    """把一段文字投成 external-call 卡片，交给网页 AI。

    @param source 通道标识
    @param openid 接收方标识
    @param text   正文
    @param title  卡片标题；缺省按通道名生成
    @param extra  附加到 payload 的字段（如 msg_id）
    @returns 卡片 id；失败返回空串
    """
    import json
    payload = {"source": source, "openid": openid}
    if extra:
        payload.update(extra)
    try:
        card = card_bus.bus.create(
            source=source,
            card_type="external-call",
            title=title or (source + " 用户"),
            content=json.dumps(payload, ensure_ascii=False, indent=2)
                    if not text else text,
            payload=payload,
        )
        log("已投递文本卡片", card.id[:8])
        return card.id
    except Exception as e:
        log("投递文本卡片失败：", e)
        return ""
