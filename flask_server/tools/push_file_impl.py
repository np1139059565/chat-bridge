"""AI 工具调用镜像插件 —— push_file 工具实现

职责：把电脑上的一个本地文件推送到用户的手机 QQ，供其下载。

背景：图片与语音已能推到 QQ（见 remote_bridge/qq_media.py），
本工具把同一套「上传富媒体 → 发送」链路扩展到普通文件，
使 AI 可以主动把生成的压缩包、Markdown 文档等交付给手机。

设计要点：
- 只放行白名单扩展名：先支持 .zip / .md，避免误推任意文件（如密钥、可执行文件）；
- 推送目标沿用桥接层「最近发消息的人」，无需工具显式传 openid；
- 被动回复窗口过期时 QQ 不允许主动推送，此时把原因如实回给调用方。

拆出独立模块的原因：与 memory_search_impl / run_command_impl 一致，
保持「声明（tool_meta）与实现分离」，也避免 tools_impl 超出行数上限。
"""
import os

from tool_helpers import ToolParamError, abspath as _abspath, require as _require


# 允许推送的扩展名白名单（小写，带前导点）。
# 后续要支持更多类型时只需在此追加，无需改动推送逻辑。
ALLOWED_EXTS = (".zip", ".md")

# 单文件体积上限默认值（字节）：50MB。
# QQ 富媒体上传对体积有限制，过大文件既慢又易失败，故在发送前拦截。
MAX_FILE_BYTES = 50 * 1024 * 1024


def _max_bytes():
    """取当前生效的体积上限（字节）。

    优先读设置页配置 push_file.max_bytes；配置不可用时退回模块常量，
    保证工具在任何环境下都有明确上限、不会无限制上传。
    @returns 体积上限（字节）
    """
    try:
        import tool_config
        v = tool_config.get_value("push_file", "max_bytes")
        return int(v) if v else MAX_FILE_BYTES
    except Exception:
        return MAX_FILE_BYTES


def _suffix(path):
    """取文件小写扩展名（带前导点）。

    @param path 文件路径
    @returns 小写扩展名；无扩展名返回空串
    """
    return os.path.splitext(str(path or ""))[1].lower()


def t_push_file(p):
    """把本地文件推送到用户手机 QQ。

    流程：校验路径 → 校验类型白名单 → 校验体积 → 取桥接上下文 → 发送。
    @param p 参数：path（必填）
    @return { pushed, name, size, target, note? }
    """
    # 参数校验：路径必填，缺失时由 require 抛参数错误（归类 parameter）
    _require(p, "path")
    fp = _abspath(p.get("path"))

    # 存在性校验：给出明确原因，避免调用方反复试错
    if not os.path.isfile(fp):
        raise ToolParamError("文件不存在：%s" % fp)

    # 类型白名单：防止把任意文件（密钥、脚本、可执行体）推到手机上
    ext = _suffix(fp)
    if ext not in ALLOWED_EXTS:
        raise ToolParamError(
            "不支持的文件类型 %s，当前仅支持：%s"
            % (ext or "（无扩展名）", "、".join(ALLOWED_EXTS))
        )

    # 体积校验：超大文件上传耗时长且易被平台拒绝，提前拦截并说明
    size = os.path.getsize(fp)
    limit = _max_bytes()
    if size > limit:
        raise ToolParamError(
            "文件过大（%.1fMB），上限 %.1fMB"
            % (size / 1048576.0, limit / 1048576.0)
        )

    # 取桥接上下文：客户端句柄与推送目标都来自「最近一次 QQ 交互」
    from remote_bridge import message_router as mr
    client = mr.get_last_client()
    openid = mr.get_last_openid()
    # 桥接未启用或从未收到过 QQ 消息：没有可用的推送目标
    if not client or not openid:
        raise ToolParamError(
            "远程桥接尚未就绪：请先在手机 QQ 里给机器人发一条消息，再重试"
        )

    # 真正发送：失败原因（如窗口过期）如实回给调用方，便于转述给用户
    ok, data = mr.push_file(client, openid, fp)
    out = {
        "pushed": bool(ok),
        "name": os.path.basename(fp),
        "size": size,
        "target": "QQ",
    }
    if not ok:
        out["error"] = str(data)
        out["note"] = "推送未成功，文件仍保留在电脑上，可稍后重试"
    return out
