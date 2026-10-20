"""AI 工具调用镜像插件 —— 文件读取类工具实现

职责：read_file（分段 / 批量）与 read_image（图片转 dataURL）的落地。

为何独立成模块：
- 文件读取涉及分段、批量与体积判定，逻辑自成一体；
- 主模块 tools_impl.py 需保持在仓库行数上限内，故按既有约定
  （run_command_impl / memory_search_impl / memory_quality_impl）拆出并重导出。

路径口径：绝对路径原样，相对路径以工程根为基准（与写文件类工具一致）。
"""
import base64
import os

import screenshot_store
from tool_helpers import (
    ToolParamError,
    abspath as _abspath,
    normalize_aliases as _normalize_aliases,
    require as _require,
    enforce_size_limit,
)

# 单次批量读取的文件数上限：防止一次请求把海量文件拼成超大结果
MAX_BATCH_FILES = 20


def _read_text_segment(fp, offset, limit):
    """按行读取文件片段（fp 为绝对路径），返回内容与行数。"""
    offset = int(offset or 1)
    with open(fp, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    start = max(0, offset - 1)
    end = len(lines) if limit is None else start + int(limit)
    return {
        "path": str(fp),
        "content": "".join(lines[start:end]),
        "total_lines": len(lines),
        "_read_lines": max(0, end - start),
    }


def _load_one(file_path, offset, limit):
    """读取单个文件片段，返回组装用的原始信息（不做体积判定）。

    @param file_path 文件路径（绝对路径原样，相对路径以工程根为基准）
    @param offset    起始行（从 1 开始）
    @param limit     读取行数
    @returns {path, lines, total_lines, content, read_lines}
    """
    fp = _abspath(file_path)
    res = _read_text_segment(fp, offset, limit)
    read_lines = res.pop("_read_lines")
    start_line = max(1, int(offset or 1))
    end_line = (start_line + read_lines - 1) if read_lines else start_line
    return {
        "path": res["path"],
        "lines": [start_line, end_line],
        "total_lines": res["total_lines"],
        "content": res["content"],
        "read_lines": read_lines,
    }


def t_read_file(p):
    """读取文件内容，支持 offset / limit 分段，支持一次读取多个文件。

    路径口径与写文件类工具保持一致：绝对路径原样使用，相对路径以工程根为基准解析。

    返回结构与截图工具对称：正文放在 data.text，由前端取出后粘贴进对话；
    回传给 AI 的只有精简的 bridge-chat-res 标记。体积上限沿用统一的
    limits.max_json_chars（界面可配），超限时提示缩小读取范围。
    """
    _normalize_aliases(p)
    offset = p.get("offset", 1)
    limit = p.get("limit")

    # 批量模式：file_paths 为数组，一次读取多个文件，减少往返次数
    paths_param = p.get("file_paths")
    if paths_param:
        if not isinstance(paths_param, list):
            raise ToolParamError("file_paths 必须是字符串数组")
        if len(paths_param) > MAX_BATCH_FILES:
            raise ToolParamError(
                "一次最多读取 %d 个文件，当前传入 %d 个" % (MAX_BATCH_FILES, len(paths_param))
            )
        chunks = []
        metas = []
        total_lines_read = 0
        max_total = 0
        for one in paths_param:
            it = _load_one(one, offset, limit)
            total_lines_read += it["read_lines"]
            max_total = max(max_total, it["total_lines"])
            # 每段带「路径 行范围」头，便于在对话中区分来源
            chunks.append("===== %s 行 %d-%d =====\n%s" % (
                it["path"], it["lines"][0], it["lines"][1], it["content"]))
            metas.append({"path": it["path"], "lines": it["lines"],
                          "total_lines": it["total_lines"]})
        return enforce_size_limit(
            {"data": {"text": "\n\n".join(chunks)}, "count": len(metas), "files": metas},
            "请减少读取范围后重试：减少 file_paths 个数，或用 offset / limit 分段读取；"
            "本次读取 %d 个文件、共约 %d 行。" % (len(metas), total_lines_read),
        )

    # 单文件模式
    _require(p, "file_path")
    it = _load_one(p.get("file_path"), offset, limit)
    return enforce_size_limit(
        {
            "data": {"text": it["content"]},
            "path": it["path"],
            "lines": it["lines"],
            "total_lines": it["total_lines"],
        },
        "请减少读取行数后重试：用 offset 指定起始行、limit 指定读取行数，分段读取；"
        "本次读取约 %d 行（文件共 %d 行），请改读更少的行。"
        % (it["read_lines"], it["total_lines"]),
    )


# 图片读取体积上限（字节）：超过则拒绝，避免超大文件撑爆 HTTP 响应与前端内存
MAX_IMAGE_BYTES = 10 * 1024 * 1024

# 允许读取的图片扩展名 → MIME 类型（与前端可粘贴的图片类型保持一致）
IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def t_read_image(p):
    """读取本地图片，转 dataURL 后走截图粘贴链路送进网页 AI。

    结果结构与 get_page_snapshot 对齐（data.screenshot + data.saved）：
    前端沿用既有截图分支，把图片贴入输入框、正文只带极短的 bridge-chat-res
    标记，图片二进制不进入对话正文。

    不调用 enforce_size_limit：dataURL 必然超过通用 JSON 上限，但它只在
    「后端 → 前端」这一跳传输，前端只回传精简标记，不会膨胀对话上下文。
    体积控制改由 MAX_IMAGE_BYTES 在读取前拦截。
    """
    _normalize_aliases(p)
    _require(p, "file_path")
    fp = _abspath(p.get("file_path"))
    # 路径校验：必须是已存在的普通文件
    if not os.path.isfile(fp):
        raise ToolParamError("文件不存在：%s" % p.get("file_path"))
    # 格式校验：只接受白名单内的图片类型
    ext = os.path.splitext(fp)[1].lower()
    mime = IMAGE_MIME.get(ext)
    if not mime:
        raise ToolParamError(
            "不支持的图片格式 %s；支持：%s" % (ext or "(无扩展名)", "、".join(sorted(IMAGE_MIME)))
        )
    # 体积校验：超限直接报错，提示先压缩
    size = os.path.getsize(fp)
    if size > MAX_IMAGE_BYTES:
        raise ToolParamError(
            "图片体积 %.1fMB 超过上限 %dMB，请先压缩后再读取"
            % (size / 1048576.0, MAX_IMAGE_BYTES // 1048576)
        )
    # 读原始字节并编码成 dataURL
    with open(fp, "rb") as fh:
        raw = fh.read()
    data_url = "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode("ascii"))
    # 落盘：前端按文件名把图片挂回消息（pendingImages），与截图链路同一目录口径
    saved = screenshot_store.save_data_url(data_url)
    return {
        "data": {
            "screenshot": data_url,
            "saved": ({"name": saved["name"], "path": saved["path"]} if saved else None),
        },
        "path": str(fp),
        "size": size,
        "mime": mime,
    }
