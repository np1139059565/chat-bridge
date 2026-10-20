"""AI 工具调用镜像插件 —— 文件读取类工具实现

职责：read_file（分段 / 批量）与 read_image（图片转 dataURL）的落地。

为何独立成模块：
- 文件读取涉及分段、批量与体积判定，逻辑自成一体；
- 主模块 tools_impl.py 需保持在仓库行数上限内，故按既有约定
  （run_command_impl / memory_search_impl / memory_quality_impl）拆出并重导出。

正文传递方式（与截图一致）：
- 正文不放进工具结果，而是转成 dataURL 放在 data.screenshot；
- 前端按同一条粘贴链路把正文作为文件附件贴进输入框，
  AI 看到的是附件而非对话正文，工具结果本身保持极小。

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
    """读取单个文件片段，返回组装用的原始信息（不做体积判定）。"""
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


def _check_whole_size(fp):
    """整文件读取的体积校验：沿用统一的 limits.max_json_chars 上限。

    整文件不返回内容，但文件过大时一次取回也会撑爆前端内存，
    故按同一配置在上限处拦截，提示改用分段读取。
    @param fp 源文件绝对路径
    """
    from tool_helpers import max_json_chars
    limit = max_json_chars()
    size = os.path.getsize(fp)
    if size > limit:
        raise ToolParamError(
            "文件约 %d 字节，超过单次读取上限 %d；请用 offset / limit 分段读取。"
            % (size, limit)
        )


def _as_source_ref(fp):
    """整文件读取：只返回源文件引用，不读内容、不编码、不生成任何副本。

    前端按 path 经 /api/web/source-file 取原始字节，直接构造 File 粘贴，
    省去 base64 往返与额外落盘。
    @param fp 源文件绝对路径
    @returns 文件引用信息 {mime, name, path, source}
    """
    return {
        "mime": "text/plain",
        "name": os.path.basename(fp) or "file.txt",
        "path": str(fp),
        "source": True,
    }


def _as_file_payload(text, file_name, meta):
    """把正文包装成「文件附件」结果，供前端作为文件粘贴进输入框。

    与截图各自独立：截图用 data.screenshot + data.saved（需落盘回挂），
    文件附件用 data.file，字段与语义都不共用，避免两种功能互相污染。
    - data.file.mime    附件 MIME（text/plain）
    - data.file.name    附件文件名（原文件名，便于 AI 识别）
    - data.file.content 正文的 dataURL
    - 结果本身只带路径、行数与文件名，不含正文明文。
    @param text      正文（已按需拼接好）
    @param file_name 附件文件名
    @param meta      额外元信息（路径、行范围、总数等）
    @returns 工具结果字典
    """
    raw = text.encode("utf-8")
    data_url = "data:text/plain;base64," + base64.b64encode(raw).decode("ascii")
    # 文本附件不落盘：dataURL 已在结果里，前端直接据此构造 File 粘贴。
    # 落盘只对截图有意义（镜像按文件名回挂图片），文本挂回去会渲染出错误内容。
    out = {
        "data": {
            "file": {
                "mime": "text/plain",
                "name": file_name,
                "content": data_url,
            },
        },
    }
    out.update(meta or {})
    return out


def _is_whole_file(offset, limit):
    """判断本次请求是否为「整文件」读取（未指定 limit 且从头开始）。

    @param offset 起始行
    @param limit  读取行数；None 表示不限
    @returns 整文件读取返回 True
    """
    return limit is None and int(offset or 1) <= 1


def _read_batch_whole(paths_param):
    """批量整文件读取：每个文件只给源文件引用，不读内容、不生成副本。

    @param paths_param 文件路径列表
    @returns 工具结果字典
    """
    refs = []
    for one in paths_param:
        fp = _abspath(one)
        # 路径校验：必须是已存在的普通文件
        if not os.path.isfile(fp):
            raise ToolParamError("文件不存在：%s" % one)
        # 体积校验：整文件虽不回传内容，但过大也会撑爆前端内存
        _check_whole_size(fp)
        refs.append(_as_source_ref(fp))
    return {"data": {"files": refs}, "count": len(refs)}


def _read_batch_segment(paths_param, offset, limit):
    """批量分段读取：逐文件取片段，拼成一份带来源标注的文本附件。

    @param paths_param 文件路径列表
    @param offset      起始行
    @param limit       读取行数
    @returns 工具结果字典
    """
    chunks = []      # 各文件正文片段，带「路径 行范围」头
    metas = []       # 各文件的行范围与总行数元信息
    total_lines_read = 0
    for one in paths_param:
        it = _load_one(one, offset, limit)
        total_lines_read += it["read_lines"]
        # 每段带「路径 行范围」头，便于在附件中区分来源
        chunks.append("===== %s 行 %d-%d =====\n%s" % (
            it["path"], it["lines"][0], it["lines"][1], it["content"]))
        metas.append({"path": it["path"], "lines": it["lines"],
                      "total_lines": it["total_lines"]})
    joined = "\n\n".join(chunks)
    # 体积校验：超限时报错并提示缩小范围
    enforce_size_limit(
        {"data": {"text": joined}},
        "请减少读取范围后重试：减少 file_paths 个数，或用 offset / limit 分段读取；"
        "本次读取 %d 个文件、共约 %d 行。" % (len(metas), total_lines_read),
    )
    return _as_file_payload(
        joined, "%d_files_%d-%d.txt" % (len(metas), offset, offset + total_lines_read - 1),
        {"count": len(metas), "files": metas, "total_lines": total_lines_read},
    )


def _read_single_whole(raw_path):
    """单个整文件读取：只给源文件引用，不读内容也不生成副本。

    前端按路径取原始字节后直接构造 File 粘贴，省去 base64 往返与额外落盘。
    @param raw_path 请求里的原始路径（用于报错提示）
    @returns 工具结果字典
    """
    fp = _abspath(raw_path)
    # 路径校验：必须是已存在的普通文件
    if not os.path.isfile(fp):
        raise ToolParamError("文件不存在：%s" % raw_path)
    # 体积校验：过大时提示改用分段读取
    _check_whole_size(fp)
    return {"data": {"file": _as_source_ref(fp)}}


def _read_single_segment(raw_path, offset, limit):
    """单个文件分段读取：生成片段内容，作为文本附件交由前端粘贴。

    @param raw_path 请求里的原始路径
    @param offset   起始行
    @param limit    读取行数
    @returns 工具结果字典
    """
    it = _load_one(raw_path, offset, limit)
    # 体积校验：超限时报错并提示缩小范围
    enforce_size_limit(
        {"data": {"text": it["content"]}},
        "请减少读取行数后重试：用 offset 指定起始行、limit 指定读取行数，分段读取；"
        "本次读取约 %d 行（文件共 %d 行），请改读更少的行。"
        % (it["read_lines"], it["total_lines"]),
    )
    # 分段读取：文件名带上行号范围，一眼可辨这不是整个文件
    base_name = "%s_%d-%d.txt" % (
        os.path.basename(it["path"]) or "file", it["lines"][0], it["lines"][1])
    return _as_file_payload(
        it["content"], base_name,
        {"path": it["path"], "lines": it["lines"], "total_lines": it["total_lines"]},
    )


def t_read_file(p):
    """读取文件内容，支持 offset / limit 分段，支持一次读取多个文件。

    正文不随工具结果回传：转成 dataURL 放在 data.screenshot，由前端按与截图
    相同的粘贴链路贴进输入框。体积上限沿用统一的 limits.max_json_chars
    （界面可配），超限时提示缩小读取范围。

    按「批量 / 单个」与「整文件 / 分段」两个维度共四种组合分发到对应实现。
    """
    _normalize_aliases(p)
    offset = p.get("offset", 1)
    limit = p.get("limit")
    # 批量模式：file_paths 为数组，一次读取多个文件，减少往返次数
    paths_param = p.get("file_paths")
    if paths_param:
        # 类型与数量校验
        if not isinstance(paths_param, list):
            raise ToolParamError("file_paths 必须是字符串数组")
        if len(paths_param) > MAX_BATCH_FILES:
            raise ToolParamError(
                "一次最多读取 %d 个文件，当前传入 %d 个" % (MAX_BATCH_FILES, len(paths_param))
            )
        # 整文件批量与分段批量各自处理
        if _is_whole_file(offset, limit):
            return _read_batch_whole(paths_param)
        return _read_batch_segment(paths_param, offset, limit)
    # 单文件模式
    _require(p, "file_path")
    raw_path = p.get("file_path")
    # 整文件与分段各自处理
    if _is_whole_file(offset, limit):
        return _read_single_whole(raw_path)
    return _read_single_segment(raw_path, offset, limit)


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
            "file_name": os.path.basename(fp),
        },
        "path": str(fp),
        "size": size,
        "mime": mime,
    }
