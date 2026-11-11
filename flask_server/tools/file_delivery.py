"""AI 工具调用镜像插件 —— 文件正文投递方式

职责：决定 read_file 的正文以何种形式回到调用方。

两种投递方式：
    附件粘贴（默认）——正文落盘或给源文件引用，前端按路径取回后
                        作为文件附件贴进网页 AI 输入框；
    结果直返       ——正文直接随工具结果返回。

走哪一条由三个条件共同决定：当前站点档案未禁用附件粘贴（filePaste）、
设置页开关 paste_delivery 开启、文件扩展名属于 file_types 的可粘贴清单。
任一不成立都走结果直返——部分网页 AI 不接收 paste 事件里的文件，
硬贴会静默丢内容，比直返更糟。

拆出本模块的原因：投递方式是一套独立的关注点，与「怎么读文件」正交；
放进 file_read_impl 会让该文件超出仓库的行数上限。
"""
import os

from tool_helpers import ToolParamError, enforce_size_limit


# 配置键名：设置页据此渲染开关
PASTE_KEY = "paste_delivery"


def paste_enabled():
    """当前是否以附件粘贴方式投递正文。

    配置不可用或未设置时按开启处理，保持既有行为不变。
    @returns 开启粘贴投递返回 True
    """
    try:
        import tool_config
        v = tool_config.get_value("read_file", PASTE_KEY)
        return True if v is None else bool(v)
    except Exception:
        return True


def _current_host():
    """取本次工具调用所在网页的地址（/tool 请求体的 host_page_url）。

    非 HTTP 调用（QQ 指令、定时任务）没有请求上下文，返回空串；
    此时不做站点级判定，沿用全局开关，行为与改造前一致。
    """
    try:
        from flask import request
        data = request.get_json(force=True, silent=True) or {}
        return str(data.get("host_page_url") or data.get("page_url") or "")
    except Exception:
        return ""


def _site_allows_paste(url):
    """该站点是否支持把文件作为附件贴进输入框。

    档案字段 filePaste 显式为 False 时禁用；缺省 / 为真均视为支持。
    域名经 site_profiles 映射回档案 id，查不到就退回全局口径。
    """
    if not url:
        return True
    try:
        import runtime
        from urllib.parse import urlparse
        hn = (urlparse(url if "://" in url else "//" + url).hostname or url).lower()
        pid = (runtime.CONFIG.get("site_profiles") or {}).get(hn)
        if not pid:
            return True
        prof = (runtime.CONFIG.get("profiles") or {}).get(pid) or {}
        val = prof.get("filePaste", True)
        # 设置页草稿可能把布尔转成文本（"false"），严格 is not False 会让禁用失效；
        # 故一并识别字符串形态，保证「勾掉 -> 覆盖 -> 真的直返」闭环。
        if isinstance(val, str):
            return val.strip().lower() not in ("false", "0", "no", "off")
        return val is not False
    except Exception:
        return True


def should_paste(file_path):
    """判断某文件本次是否以附件粘贴方式投递。

    三道同时成立才走粘贴：站点未禁用附件粘贴、全局开关开启、
    扩展名属于可粘贴清单。任一不成立改走结果直返。
    @param file_path 文件路径
    @returns 走附件粘贴返回 True
    """
    if not _site_allows_paste(_current_host()):
        return False
    if not paste_enabled():
        return False
    from file_types import is_pasteable
    return is_pasteable(file_path)


def as_inline_payload(text, file_name, meta):
    """把正文直接放进工具结果，不经附件粘贴链路。

    @param text      正文
    @param file_name 原文件名（仅用于元信息展示）
    @param meta      额外元信息（路径、行范围、总数等）
    @returns 工具结果字典，含 content 字段
    """
    out = {"content": str(text or ""), "name": file_name}
    out.update(meta or {})
    return out


def read_whole_text(fp):
    """读取整文件正文，供结果直返模式使用。

    编码容错与分段读取保持一致：非法字节以替换字符呈现，不让整次读取失败。
    @param fp 源文件绝对路径
    @returns 全文文本
    """
    with open(fp, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def whole_file_inline(fp, guidance):
    """整文件直返：读取全文、校验体积后包装为结果。

    @param fp       源文件绝对路径
    @param guidance 超限时给调用方的收敛建议
    @returns 工具结果字典
    """
    text = read_whole_text(fp)
    enforce_size_limit({"content": text}, guidance)
    return as_inline_payload(text, os.path.basename(fp) or "file.txt", {"path": str(fp)})


# 体积超限时的收敛建议：整文件读取无法再缩小，只能改成分段
WHOLE_FILE_GUIDANCE = "请用 offset / limit 分段读取后重试；本次为整文件读取。"


__all__ = [
    "PASTE_KEY",
    "paste_enabled",
    "should_paste",
    "as_inline_payload",
    "read_whole_text",
    "whole_file_inline",
    "WHOLE_FILE_GUIDANCE",
    "ToolParamError",
]
