"""远程桥接 —— 网页消息内图片的推送

从 message_router.py 抽出，使该文件保持在行数上限内。

职责：把采集端解析出的 image 块（dataURL / http(s) 地址）落盘，再发回 QQ。
blob: 等网页进程内的临时地址后端无法访问，跳过并记日志。
调用方是 message_router.py；push_image 由调用方注入，避免模块间循环导入。
"""
import os
import time

from . import bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][router]", *args)


def _save_src_to_file(src):
    """把图片地址落盘为本地文件，返回路径；无法获取时返回空串。

    dataURL：直接解码写盘。
    http(s)：下载到 QQ 图片目录。
    其它（blob: 等）：返回空串，由调用方跳过。
    @param src 图片地址
    @returns 本地文件路径；失败返回空串
    """
    if not src:
        return ""
    if src.startswith("data:image/"):
        import screenshot_store
        saved = screenshot_store.save_data_url(src)
        return (saved or {}).get("path") or ""
    if src.startswith("http://") or src.startswith("https://"):
        import paths
        from .qq_gateway import _download_file
        os.makedirs(str(paths.QQ_IMAGES_DIR), exist_ok=True)
        ext = ".png"
        low = src.lower().split("?")[0]
        for e in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            if low.endswith(e):
                ext = e
                break
        dest = str(paths.QQ_IMAGES_DIR / ("web_" + str(int(time.time() * 1000)) + ext))
        return dest if _download_file(src, dest) else ""
    return ""


def push_message_images(qq_client, openid, m, push, push_image):
    """把一条消息里的图片块推送到 QQ。

    采集端把网页图片解析成 {type:'image', src} 块；此前推 QQ 只拼文本，
    图片被整段忽略（与抽屉缺图同一根因）。这里把可获取的图片落盘后发原图。
    @param m 消息对象
    @param push 推送开关字典
    @param push_image 发送图片的函数（由调用方注入，避免循环导入）
    @returns 成功推送的图片张数
    """
    if not push.get("tool", True):
        return 0
    blocks = m.get("blocks") or []
    sent = 0
    for b in blocks:
        if not b or b.get("type") != "image":
            continue
        src = str(b.get("src") or "")
        path = _save_src_to_file(src)
        if not path:
            if src:
                log("图片地址后端不可达，跳过推送：", src[:40])
            continue
        if push_image(qq_client, openid, path):
            sent += 1
    return sent
