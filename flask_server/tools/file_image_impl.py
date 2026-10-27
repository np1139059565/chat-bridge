"""AI 工具调用镜像插件 —— 图片读取工具实现

职责：read_image 的落地——读取本地图片、转 dataURL、落盘并回传截图引用。

为何独立成模块：
- 图片读取与文本读取的链路完全不同：文本给「文件附件」引用，图片走「截图」链路；
- 两者的体积上限、校验规则、结果结构各自独立，混在一个文件里既超长也难改。

结果结构（与 get_page_snapshot 对齐）：data.screenshot_url + data.saved。
前端沿用既有截图分支，把图片贴入输入框；图片二进制不进入对话正文。

路径口径：绝对路径原样，相对路径以工程根为基准（与其它文件类工具一致）。
"""
import base64
import os

import screenshot_store
from tool_helpers import (
    ToolParamError,
    abspath as _abspath,
    require as _require,
)

# 图片读取体积上限默认值（字节）：超过则拒绝，避免超大文件撑爆 HTTP 响应与前端内存。
# 实际取值由 tool_config 的声明覆盖（设置页可调），此常量仅作兜底。
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


def _image_limit():
    """取当前生效的图片体积上限；配置不可用时回退常量。"""
    try:
        import tool_config
        v = tool_config.get_value("read_image", "max_bytes")
        return int(v) if v else MAX_IMAGE_BYTES
    except Exception:
        return MAX_IMAGE_BYTES


def t_read_image(p):
    """读取本地图片，转 dataURL 后走截图粘贴链路送进网页 AI。

    结果结构与 get_page_snapshot 对齐（data.screenshot_url + data.saved）：
    前端沿用既有截图分支，把图片贴入输入框、正文只带极短的 bridge-chat-res
    标记，图片二进制不进入对话正文。

    不调用 enforce_size_limit：dataURL 必然超过通用 JSON 上限，但它只在
    「后端 → 前端」这一跳传输，前端只回传精简标记，不会膨胀对话上下文。
    体积控制改由 MAX_IMAGE_BYTES 在读取前拦截。
    """
    _require(p, "path")
    fp = _abspath(p.get("path"))
    # 路径校验：必须是已存在的普通文件
    if not os.path.isfile(fp):
        raise ToolParamError("文件不存在：%s" % p.get("path"))
    # 格式校验：只接受白名单内的图片类型
    ext = os.path.splitext(fp)[1].lower()
    mime = IMAGE_MIME.get(ext)
    if not mime:
        raise ToolParamError(
            "不支持的图片格式 %s；支持：%s" % (ext or "(无扩展名)", "、".join(sorted(IMAGE_MIME)))
        )
    # 体积校验：超限直接报错，提示先压缩。上限取当前配置值（设置页可调）。
    limit_bytes = _image_limit()
    size = os.path.getsize(fp)
    if size > limit_bytes:
        raise ToolParamError(
            "图片体积 %.1fMB 超过上限 %dMB，请先压缩后再读取"
            % (size / 1048576.0, limit_bytes // 1048576)
        )
    # 读原始字节并编码成 dataURL（仅用于落盘，不再返回给前端）
    with open(fp, "rb") as fh:
        raw = fh.read()
    data_url = "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode("ascii"))
    # 落盘：前端按文件名把图片挂回消息（pendingImages），与截图链路同一目录口径
    saved = screenshot_store.save_data_url(data_url)
    return {
        "data": {
            # 不返回巨大的 base64 长串，只返回文件的相对路径供前端拉取
            "screenshot_url": "/api/web/screenshot-file/%s" % saved["name"] if saved else "",
            "saved": ({"name": saved["name"], "path": saved["path"]} if saved else None),
            "file_name": os.path.basename(fp),
        },
        "path": str(fp),
        "size": size,
        "mime": mime,
    }
