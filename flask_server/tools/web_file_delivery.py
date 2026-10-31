"""AI 工具调用镜像插件 —— 网页版文件交付

职责：把本地文件复制进网页下载目录，并给出一条可点击的下载链接。
供 push_file 在「最近活跃客户端是网页」时调用。

与 QQ 推送的分工：
- QQ：走 remote_bridge 的上传富媒体 → 发送链路，需要客户端与被动回复窗口；
- 网页：文件落进 WEB_FILES_DIR，由 /api/web/file-download 按文件名下发，
  手机浏览器点链接即下载。网页侧不依赖任何「最近一次交互句柄」。

文件名策略：原名 + 时间戳后缀。
同一文件多次推送不会互相覆盖，也不与历史文件重名；
时间戳使文件名唯一，可安全使用强缓存（内容不变）。
"""
import os
import shutil
import time

import paths


def _suffix(name):
    """取文件扩展名（含前导点）；无扩展名返回空串。"""
    _, ext = os.path.splitext(name)
    return ext


def _safe_stem(name):
    """取不含目录与扩展名的主名，并过滤路径分隔符等危险字符。

    仅用于拼装落盘名，因此只保留基名并替换掉可能被当作路径的字符。
    @param name 原始文件名
    @returns 安全主名；为空时回退为 file
    """
    stem = os.path.splitext(os.path.basename(name or ""))[0]
    # 逐个替换可能被解释为路径分隔或非法的字符，避免落盘时越出目录
    for ch in ('/', '\\', ':', '*', '?', '"', '<', '>', '|'):
        stem = stem.replace(ch, '_')
    stem = stem.strip()
    return stem or "file"


def save_for_web(src_path):
    """把源文件复制进网页下载目录，返回落盘信息。

    @param src_path 源文件绝对路径（Path 或 str）
    @returns { name, size }；name 为落盘文件名，供拼下载链接
    @raises OSError 目录创建或复制失败时抛出，由调用方转成工具错误
    """
    src = str(src_path)
    # 目录可能首次使用：按需创建，避免首次推送因目录不存在而失败
    paths.WEB_FILES_DIR.mkdir(parents=True, exist_ok=True)
    base = os.path.basename(src)
    # 落盘名 = 安全主名 + 时间戳 + 原扩展名：既保留可读性，又保证唯一
    stem = _safe_stem(base)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = "%s-%s%s" % (stem, stamp, _suffix(base))
    dest = paths.WEB_FILES_DIR / name
    # 极端情况下同一秒内同名文件重复推送：追加序号直到不重名
    n = 1
    while dest.exists():
        name = "%s-%s-%d%s" % (stem, stamp, n, _suffix(base))
        dest = paths.WEB_FILES_DIR / name
        n += 1
    shutil.copy2(src, dest)
    size = os.path.getsize(dest)
    # 交付后按数量上限回收旧文件：下载目录只增不减会持续占盘。
    # 回收失败不影响本次交付（文件已就位），故吞掉异常。
    _prune()
    return {"name": name, "size": size}


def _prune():
    """按上限回收网页下载目录中的旧文件。

    复用 core/file_prune 的统一实现（数量上限 + 引用保护）；
    此处无引用保护对象：下载链接是一次性的，旧链接失效可接受。
    """
    try:
        from app_limits import MAX_WEB_FILES
        from file_prune import prune_dir
        prune_dir(paths.WEB_FILES_DIR, MAX_WEB_FILES)
    except Exception:
        # 回收是尽力而为，失败不应让交付本身失败
        pass


def download_url(name):
    """拼出网页下载链接。

    刻意返回相对路径：手机浏览器渲染消息时会基于当前页面地址解析，
    主机与端口自动跟随用户实际访问的地址。若在此写死绝对地址，
    服务换机、换 IP 或换端口后链接即刻失效（曾因此把链接指向了另一台机器的 IP）。
    """
    return "/api/web/file-download/%s" % name


def notify_inbox(name, original):
    """把「文件已就绪」这条消息直接投进网页收件箱。

    为什么不靠 AI 在回复里复述链接：AI 复述多一道转述环节，
    既多一轮往返，也可能把地址抄错。由工具直接投递，
    用户看到的就是可点击的下载条目。
    @param name     下载目录中的落盘文件名
    @param original 用户可读的原始文件名
    """
    try:
        from web_bridge import web_inbox
        # 用 system 角色：这是工具产出的交付消息，与 AI 正文区分开，
        # 也不会触发「最近活跃渠道」登记（登记只认 user）。
        web_inbox.append(
            "system",
            "文件已就绪，点击下载：[%s](%s)" % (original, download_url(name)),
            kind="file-delivery",
        )
    except Exception:
        # 投递失败不影响文件本身已落盘；用户仍可凭返回的链接手动下载
        pass
