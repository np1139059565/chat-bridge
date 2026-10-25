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
# 正文投递方式（附件粘贴 / 结果直返）集中在该模块，与读取逻辑解耦
from file_delivery import (
    paste_enabled as _paste_enabled,
    as_inline_payload as _as_inline_payload,
    read_whole_text as _read_whole_text,
    whole_file_inline as _whole_file_inline,
    WHOLE_FILE_GUIDANCE,
)

# 单次批量读取的文件数上限默认值：防止一次请求把海量文件拼成超大结果。
# 实际取值由 tool_config 的声明覆盖（设置页可调），此常量仅作兜底。
MAX_BATCH_FILES = 20


def _batch_limit():
    """取当前生效的批量读取上限；配置不可用时回退常量。"""
    try:
        import tool_config
        v = tool_config.get_value("read_file", "max_batch_files")
        return int(v) if v else MAX_BATCH_FILES
    except Exception:
        return MAX_BATCH_FILES


def _read_text_segment(fp, offset, limit):
    """按行流式读取文件片段（fp 为绝对路径），返回内容与行数。

    逐行迭代而非一次 readlines()：大文件只取一小段时，内存占用只与
    实际读取行数相关，不会因为文件有几万行就整份载入。
    total_lines 仍为全文件行数，需完整遍历一遍才准确，故与读取同步统计。
    @param fp     源文件绝对路径
    @param offset 起始行（从 1 开始）
    @param limit  读取行数；None 表示读到末尾
    @returns dict：path / content / total_lines / _read_lines
    """
    offset = int(offset or 1)
    start = max(0, offset - 1)                 # 转为 0 基下标
    want = None if limit is None else int(limit)
    picked = []                                 # 命中的行
    total = 0                                   # 全文件行数
    with open(fp, "r", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            total += 1
            # 到达起始行之前：只计数，不保留内容
            if i < start:
                continue
            # 已取够 limit 行：仍需继续计数 total_lines，故不 break
            if want is None or len(picked) < want:
                picked.append(line)
    return {
        "path": str(fp),
        "content": "".join(picked),
        "total_lines": total,
        "_read_lines": len(picked),
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


def _as_empty_payload(file_name, meta):
    """正文为空时的工具结果：只给文字说明，不产生任何附件。

    与 _as_file_payload 的区别：不落盘、不返回 data.file / data.files。
    前端只认 data.file / data.files 才会触发粘贴（见 extractFile），
    因此这里不给附件字段，粘贴链路自然不会被触发。

    为什么不干脆不落盘：空内容仍按既有归档策略写一份空文件，
    保持「每次读取都留痕」的行为一致；但归档结果不回传，不参与粘贴。

    @param file_name 原文件名（用于归档命名）
    @param meta      额外元信息（路径、行范围、总数等）
    @returns 工具结果字典，只含文字说明与元信息
    """
    # 按既有策略归档空文件：仅留痕，不进入粘贴链路
    _save_segment("", file_name)
    out = {
        "empty": True,
        "message": "文件内容为空（或所读行范围没有内容），未生成可粘贴附件。",
    }
    out.update(meta or {})
    return out


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
    # 正文为空（空文件，或 offset 已越过文件末尾）：
    # 前端拿到空附件会去粘贴，而粘贴链路取不到任何文字，直接报「未提取到文字」，
    # 导致 AI 无法继续执行。故此处只做归档、不返回附件字段，改在结果里给出文字说明。
    if not str(text or "").strip():
        return _as_empty_payload(file_name, meta)
    # 正文落盘而非内联：dataURL 若进结果，会随消息树一起被持久化，
    # 让会话对象与每次保存的请求体膨胀。改为写成一个片段文件，只回路径；
    # 前端按路径经 /api/web/segment-file 取回，重新粘贴时再还原成 File。
    saved_name = _save_segment(text, file_name)
    file_obj = {
        "mime": "text/plain",
        "name": file_name,
    }
    if saved_name:
        # 落盘成功：按「源文件」语义回路径，前端走 source 分支现取。
        # 此处须自行导入 paths：本函数不在 paths 的导入作用域内，
        # 漏导入会直接抛 NameError，前端拿不到文件、表现为「读取文件失败」。
        import paths
        file_obj["source"] = True
        file_obj["path"] = str(paths.WEB_SEGMENTS_DIR / saved_name)
    else:
        # 落盘失败（磁盘异常等）：退回内联 dataURL，保证功能不中断
        raw = text.encode("utf-8")
        file_obj["content"] = "data:text/plain;base64," + base64.b64encode(raw).decode("ascii")
    out = {"data": {"file": file_obj}}
    out.update(meta or {})
    return out


def _save_segment(text, file_name):
    """把分段正文写成片段文件，返回文件名；失败返回空串。

    文件名用「时间戳 + 原文件名」保证唯一，避免不同分段互相覆盖。
    写入前先按上限回收一次：每次新增都回收，目录大小自然收敛，
    无需额外定时器。
    @param text      片段正文
    @param file_name 原文件名（用于命名，便于辨认来源）
    @returns 落盘后的文件名；失败返回空串
    """
    try:
        import time
        import paths
        from file_prune import prune_dir
        from app_limits import MAX_SEGMENT_FILES
        # 上限取配置值，回退常量；先回收再写入，避免目录短暂超出上限太多
        limit = MAX_SEGMENT_FILES
        try:
            import tool_config
            v = tool_config.get_value("system", "max_segment_files")
            if v:
                limit = int(v)
        except Exception:
            pass
        prune_dir(paths.WEB_SEGMENTS_DIR, limit)
        paths.WEB_SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)
        # 原文件名可能含路径分隔符等非法字符，只保留安全部分
        safe = "".join(c for c in (file_name or "seg") if c.isalnum() or c in "._-") or "seg"
        name = "seg_" + str(int(time.time() * 1000)) + "_" + safe
        (paths.WEB_SEGMENTS_DIR / name).write_text(text, encoding="utf-8")
        return name
    except Exception as e:
        # 统一走 app_log：落盘失败要能在服务端日志里查到，print 只进控制台
        import app_log
        app_log.warn("[read_file]", "分段落盘失败：%s" % e)
        return ""


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
    empties = []   # 空文件：只记录，不放进附件列表（放进去会触发空内容粘贴）
    for one in paths_param:
        fp = _abspath(one)
        # 路径校验：必须是已存在的普通文件
        if not os.path.isfile(fp):
            raise ToolParamError("文件不存在：%s" % one)
        # 体积校验：整文件虽不回传内容，但过大也会撑爆前端内存
        _check_whole_size(fp)
        if os.path.getsize(fp) == 0:
            # 空文件按归档策略留痕，但不作为附件返回
            _save_segment("", os.path.basename(fp))
            empties.append(str(fp))
            continue
        if _paste_enabled():
            refs.append(_as_source_ref(fp))
        else:
            # 关闭粘贴投递：逐个文件直返正文，不产生附件引用
            refs.append(_as_inline_payload(_read_whole_text(fp), os.path.basename(fp),
                                           {"path": str(fp)}))
    out = {"data": {"files": refs}, "count": len(refs)}
    if empties:
        # 明确告知哪些文件为空，供调用方据此判断，无需再去粘贴确认
        out["empty_files"] = empties
        out["message"] = "其中 %d 个文件内容为空，未生成可粘贴附件。" % len(empties)
    return out


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
    has_body = False  # 是否真的读到非空正文（read_lines 按请求行数算，不能作判据）
    for one in paths_param:
        it = _load_one(one, offset, limit)
        total_lines_read += it["read_lines"]
        if str(it["content"] or "").strip():
            has_body = True
        # 每段带「路径 行范围」头，便于在附件中区分来源
        chunks.append("===== %s 行 %d-%d =====\n%s" % (
            it["path"], it["lines"][0], it["lines"][1], it["content"]))
        metas.append({"path": it["path"], "lines": it["lines"],
                      "total_lines": it["total_lines"]})
    joined = "\n\n".join(chunks)
    # 没读到任何非空正文（全是空文件，或 offset 越过末尾）：
    # 此时附件里只有各段的「路径 行范围」头，粘贴出去也取不到文字，
    # 故不进附件链路，直接返回文字说明。
    if not has_body:
        return _as_empty_payload(
            "%d_files_empty.txt" % len(metas),
            {"count": len(metas), "files": metas, "total_lines": 0},
        )
    # 体积校验：超限时报错并提示缩小范围
    enforce_size_limit(
        {"data": {"text": joined}},
        "请减少读取范围后重试：减少 file_paths 个数，或用 offset / limit 分段读取；"
        "本次读取 %d 个文件、共约 %d 行。" % (len(metas), total_lines_read),
    )
    batch_name = "%d_files_%d-%d.txt" % (len(metas), offset, offset + total_lines_read - 1)
    batch_meta = {"count": len(metas), "files": metas, "total_lines": total_lines_read}
    # 关闭粘贴投递：合并后的正文直接随结果返回
    if not _paste_enabled():
        return _as_inline_payload(joined, batch_name, batch_meta)
    return _as_file_payload(joined, batch_name, batch_meta)


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
    # 空文件：不返回附件引用。否则前端会按路径取回空内容再粘贴，
    # 粘贴链路取不到文字即报「未提取到文字」，使 AI 无法继续执行。
    if os.path.getsize(fp) == 0:
        return _as_empty_payload(os.path.basename(fp),
                                 {"path": str(fp), "lines": [1, 1], "total_lines": 0})
    # 关闭粘贴投递：直接返回正文，绕过附件链路
    if not _paste_enabled():
        return _whole_file_inline(fp, WHOLE_FILE_GUIDANCE)
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
    meta = {"path": it["path"], "lines": it["lines"], "total_lines": it["total_lines"]}
    # 关闭粘贴投递：分段正文直接随结果返回
    if not _paste_enabled():
        return _as_inline_payload(it["content"], base_name, meta)
    return _as_file_payload(
        it["content"], base_name,
        {"path": it["path"], "lines": it["lines"], "total_lines": it["total_lines"]},
    )


def t_read_file(p):
    """读取文件内容，支持 offset / limit 分段，支持一次读取多个文件。

    正文不随工具结果回传：整文件给源文件引用（data.file.source + path），
    分段给片段文件引用，二者都由前端按路径取回后作为文件附件贴进输入框。
    体积上限沿用统一的 limits.max_json_chars（界面可配），超限时提示缩小范围。

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
        # 上限取当前配置值（设置页可调），而非写死的常量
        limit_files = _batch_limit()
        if len(paths_param) > limit_files:
            raise ToolParamError(
                "一次最多读取 %d 个文件，当前传入 %d 个" % (limit_files, len(paths_param))
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


# 图片读取已按职责拆到独立模块 file_image_impl，此处重导出公开名，
# 使 tools_impl 与测试里的既有引用（IMAGE_MIME / MAX_IMAGE_BYTES / t_read_image）保持不变。
from file_image_impl import (  # noqa: E402  放在此处以保持文本读取代码在前
    MAX_IMAGE_BYTES,
    IMAGE_MIME,
    t_read_image,
)

