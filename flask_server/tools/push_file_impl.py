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


# 允许推送的扩展名白名单统一复用 read_file 那一套（file_types.PASTEABLE_EXTS），
# 不再各自维护：一处扩展类型，读取、粘贴、推送三处同时生效，
# 避免出现「read_file 认、push_file 不认」的口径分裂。
from file_types import PASTEABLE_EXTS, suffix_of

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

    直接委托 file_types.suffix_of：它额外处理了 .gitignore 这类
    「点开头无主名」的文件，口径与 read_file 完全一致。
    @param path 文件路径
    @returns 小写扩展名；无扩展名返回空串
    """
    return suffix_of(path)


def _push_to_web(fp, size):
    """把文件交付给网页版：复制进下载目录，返回可点击的下载链接。

    与 QQ 推送的区别：网页侧不依赖任何「最近一次交互句柄」，
    文件落盘后由下载路由按文件名下发，手机浏览器直接下载。
    @param fp   源文件绝对路径
    @param size 文件字节数（已校验过体积上限）
    @return { pushed, name, size, target, url, note? }
    """
    from web_file_delivery import save_for_web, download_url
    try:
        saved = save_for_web(fp)
    except Exception as e:
        # 落盘失败（磁盘满、权限不足等）属环境问题，如实告知并保留源文件
        raise ToolParamError("文件已校验但保存到网页下载目录失败：%s" % e)
    return {
        "pushed": True,
        "name": os.path.basename(fp),
        "size": size,
        "target": "web",
        # 相对链接：前端按当前站点拼出完整地址，手机点开即下载
        "url": download_url(saved["name"]),
        "note": "已保存到网页下载目录。请在回复中把上面 url 原样写出，供用户在手机上点击下载。",
    }


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

    # 类型校验：复用 read_file 的白名单
    ext = _suffix(fp)
    if ext not in PASTEABLE_EXTS:
        raise ToolParamError(
            "不支持的文件类型 %s；请确认扩展名在白名单内（与 read_file 共用同一份清单）"
            % (ext or "（无扩展名）")
        )

    # 体积校验：超大文件上传耗时长且易被平台拒绝，提前拦截并说明
    size = os.path.getsize(fp)
    limit = _max_bytes()
    if size > limit:
        raise ToolParamError(
            "文件过大（%.1fMB），上限 %.1fMB"
            % (size / 1048576.0, limit / 1048576.0)
        )

    # 投递方向：跟着「最后一个给机器人发消息的客户端」走。
    # 谁刚说过话，产物就推回谁那里，与语音等其它下发的口径一致。
    import active_channel
    if active_channel.is_web():
        return _push_to_web(fp, size)

    # 取桥接上下文：客户端句柄与推送目标都来自「最近一次 QQ 交互」
    from remote_bridge import message_router as mr
    client = mr.get_last_client()
    openid = mr.get_last_openid()
    # 桥接未启用或从未收到过 QQ 消息：没有可用的推送目标。
    # 这不是参数问题（path 是对的），而是推送通道尚未建立，
    # 故归为环境类，提示先建立会话而不是反复改路径。
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
