"""远程桥接 —— 本地文件推送到 QQ

从 message_router.py 抽出，使该文件保持在行数上限内。

职责：把电脑上的一个本地文件通过 QQ 富媒体链路发到用户手机，
使用与发图 / 发语音相同的被动回复窗口与序号分配器。
调用方是 message_router（重导出本函数）与工具层 push_file。
"""
from . import bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][router]", *args)


def get_last_client():
    """取最近一次活跃的 QQ 客户端引用。

    工具层（push_file）拿不到客户端实例，需要它作发送句柄；
    客户端在收到 QQ 消息与网页上报时都会被记录，故正常情况下均非空。
    @returns QQClient 实例；尚未建立连接时为 None
    """
    # 延迟导入：message_router 在本模块之上，顶层导入会形成循环
    from . import message_router
    return message_router._last_client


def push_file(qq_client, openid, path):
    """把一个本地文件推送到 QQ（与 /sp 发图同一窗口机制）。

    使用当前被动回复窗口；窗口关闭时静默跳过（等用户下次发消息再唤醒），
    与文本 / 图片推送的策略保持一致。
    @param qq_client QQClient 实例
    @param openid 目标用户
    @param path 本地文件绝对路径
    @returns (ok, error_or_data) 二元组，便于调用方把失败原因回给用户
    """
    if not qq_client or not openid or not path:
        return False, "缺少客户端 / 接收方 / 文件路径"
    # 延迟导入：next_seq 定义在 message_router，顶层导入会形成循环
    from .message_router import next_seq
    msg_id, seq = next_seq(openid)
    if not msg_id:
        # 窗口过期：QQ 不允许主动推送，只能等用户下次说话
        log("窗口已关闭，暂不推送文件")
        return False, "被动回复窗口已关闭，请先在手机 QQ 里发一条消息再试"
    ok, data = qq_client.send_c2c_file(openid, path, msg_id=msg_id, msg_seq=seq)
    if not ok:
        log("推送文件失败：", data)
    return ok, data
