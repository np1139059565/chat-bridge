"""远程桥接 —— QQ 来件接收

职责：处理用户从手机 QQ 发来的文件（文档、压缩包等），落盘后把路径告诉 AI。

与图片的关键差异：
- 图片要贴进网页 AI 输入框，让 AI「看见」；
- 文件是二进制，AI 看不见也不需要看见，它需要的是路径，
  拿到路径后自己按需调 read_file 去读。

因此本模块不做 dataURL 转换、不走粘贴链路，只做三件事：
下载 → 校验类型 → 投一张带路径的卡片。

类型校验复用 read_file 的白名单（file_types.PASTEABLE_EXTS）：
无法识别的类型直接回错误给手机，不投给网页 AI——
否则 AI 拿到一个读不了的文件会反复尝试、把对话卡住。
"""
import os
import threading
import time

import card_bus

from . import bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][file]", *args)


# 来件体积上限（字节）：20MB。
# 手机发来的文件经 QQ 中转，过大文件下载耗时长、易超时，故设上限。
MAX_INBOUND_BYTES = 20 * 1024 * 1024


def _safe_name(raw, fallback):
    """把对端给的原始文件名净化成可安全落盘的名字。

    只取基名（去掉任何目录部分），过滤路径分隔符与控制字符，
    避免对端用 ../ 之类的名字写到目录外。
    @param raw 对端提供的文件名
    @param fallback 兜底文件名
    @returns 安全文件名
    """
    name = os.path.basename(str(raw or "").replace("\\", "/"))
    # 过滤掉可能的控制字符与保留符号
    name = "".join(c for c in name if c.isprintable() and c not in '<>:"|?*')
    return name.strip() or fallback


def handle_file(gateway, openid, file_url, file_name, msg_id):
    """接收一条 QQ 文件消息（入口，立即返回）。

    下载可能耗时，放后台线程执行，不阻塞 WebSocket 回调线程。
    @param gateway   网关实例（用于回发提示）
    @param openid    发件用户
    @param file_url  文件下载地址
    @param file_name 对端提供的文件名
    @param msg_id    消息 id
    """
    threading.Thread(
        target=_worker,
        args=(gateway, openid, file_url, file_name, msg_id),
        daemon=True,
    ).start()


def _worker(gateway, openid, file_url, file_name, msg_id):
    """后台处理：下载 → 校验类型与体积 → 落盘 → 投卡片。"""
    # 延迟导入：避免模块加载期就牵扯文件系统与工具层
    import paths
    from file_types import PASTEABLE_EXTS, suffix_of
    from .qq_event_parse import download_file as _download

    # 文件名兜底：对端没给名字时用时间戳占位，扩展名校验随后会拦掉它
    safe = _safe_name(file_name, "qqfile_%d" % int(time.time() * 1000))
    ext = suffix_of(safe)

    # 类型校验前移：不下载就能判断的，先拒掉，省一次网络传输
    if ext not in PASTEABLE_EXTS:
        _reply(gateway, openid,
               "不支持的文件类型：%s\n当前仅接受文档、压缩包等白名单内的类型"
               % (ext or "（无扩展名）"))
        log("来件类型不在白名单，已拒绝：", safe)
        return

    # 落盘目录：与图片分开，避免两类产物混在一起
    os.makedirs(str(paths.QQ_FILES_DIR), exist_ok=True)
    dest = str(paths.QQ_FILES_DIR / ("in_%d_%s" % (int(time.time() * 1000), safe)))

    if not _download(file_url, dest):
        _reply(gateway, openid, "文件下载失败，请重试")
        return

    # 体积校验：下载后才知道真实大小，超限即删并回提示
    try:
        size = os.path.getsize(dest)
    except OSError:
        size = 0
    if size > MAX_INBOUND_BYTES:
        try:
            os.remove(dest)
        except OSError:
            pass
        _reply(gateway, openid,
               "文件过大（%.1fMB），上限 %.1fMB"
               % (size / 1048576.0, MAX_INBOUND_BYTES / 1048576.0))
        return

    # 投卡片：把落盘路径交给 AI，由它自己决定读不读
    _deliver_card(openid, dest, safe, size)
    _reply(gateway, openid, "已收到文件：%s，正在交给 AI 处理" % safe)


def _deliver_card(openid, path, name, size):
    """投一张 qq-file 卡片，告诉 AI 文件落在哪。

    卡片正文刻意写成一句话而非二进制：AI 需要的是路径，不是内容。
    它拿到路径后可按需调 read_file（文本类）或让用户下载（二进制类）。
    @param openid 发件用户
    @param path   本地落盘路径
    @param name   原始文件名
    @param size   体积（字节）
    """
    try:
        card = card_bus.bus.create(
            source="qq",
            card_type="qq-file",
            title="QQ 文件",
            content="用户从手机 QQ 发来文件：%s（%d 字节），已保存到 %s"
                    % (name, size, path),
            payload={
                "kind": "qq-file",
                "openid": openid,
                "path": path,
                "name": name,
                "size": size,
            },
        )
        log("已投递文件卡片", card.id[:8], "等待抽屉取走")
    except Exception as e:
        log("投递文件卡片失败：", e)


def _reply(gateway, openid, text):
    """向手机 QQ 回一条提示。

    复用网关已有的被动回复逻辑，失败只记日志不影响主流程。
    @param gateway 网关实例
    @param openid  目标用户
    @param text    提示正文
    """
    try:
        gateway._reply_voice(openid, text)
    except Exception as e:
        log("回发文件提示失败：", e)
