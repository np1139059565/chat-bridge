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
    @returns (成功张数, 可重试失败张数) 二元组：
        成功张数是真正发出去的张数；
        可重试失败张数是「有图可发、但发送返回失败」（窗口关闭 / 网络错误），
        调用方据此决定是否留待下轮重试。
        地址拿不到（blob: 等后端不可达）不计入失败：重试多少次也拿不到，
        记了只会让这条消息永远卡在待推缓存里。
    """
    # 关闭图片推送开关时什么都不做，两个计数都是零
    if not push.get("tool", True):
        return 0, 0
    blocks = m.get("blocks") or []
    sent = 0        # 成功发出的张数
    failed = 0      # 有图但发送失败、值得下轮重试的张数
    for b in blocks:
        # 跳过非图片块与空块
        if not b or b.get("type") != "image":
            continue
        src = str(b.get("src") or "")
        path = _save_src_to_file(src)
        # 地址拿不到：属于不可恢复，计跳过不计失败
        if not path:
            if src:
                log("图片地址后端不可达，跳过推送：", src[:40])
            continue
        # 真正发送：成功计入 sent，失败计入 failed 供上层重试
        if push_image(qq_client, openid, path):
            sent += 1
        else:
            failed += 1
    return sent, failed


def push_card_result(qq_client, openid, card, push):
    """推送一条工具卡片结果到 QQ。

    只处理截图类结果（发图片，与 /sp 同路）。文本结果不在此推送：
    它经「回传网页 AI → 成为一条消息 → 镜像抓取」本来就能到 QQ，
    在此再推会重复。受 tool 推送开关控制，与正文消息一致。
    @param qq_client QQClient 实例
    @param openid 目标用户
    @param card 卡片结果 {id, tool, status, path}
    @param push 推送开关字典
    @returns 是否发送成功
    """
    if not push.get("tool", True):
        return False
    img_path = card.get("path") or ""
    if not img_path:
        return False
    # 延迟导入：push_image 定义在 message_router，顶层导入会形成循环
    from .message_router import push_image
    return push_image(qq_client, openid, img_path)


def push_images_block(qq_client, openid, m, push, pushed, seen_keys):
    """推送一条消息里的图片块并记账。

    从 handle_report 内层循环抽出，避免嵌套过深；seen_keys 就地追加。
    @returns (成功张数, 是否有可重试的失败) 二元组。
        成功张数用于计入本次推送条数；
        可重试失败表示「有图可发但发送失败」，调用方据此把本条挂进待推缓存，
        下轮上报再试，避免正文已记账导致图片被永久漏掉。
    """
    mid = m.get("id") or ""
    ikey = (mid + "#img") if mid else ""
    # 已推过或本轮已记账：无需再评估，也没有失败可言
    if ikey and (ikey in pushed or ikey in seen_keys):
        return 0, False
    # 延迟导入：push_image 定义在 message_router，顶层导入会形成循环
    from .message_router import push_image
    n, failed = push_message_images(qq_client, openid, m, push, push_image)
    # 有图成功发出：整条图片记为已推，下轮不再重复评估
    if n > 0 and ikey:
        seen_keys.append(ikey)
    return n, failed
