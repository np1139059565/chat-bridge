"""网页版机器人 —— 文件上传处理

从 routes/web.py 抽出，使该文件保持在行数上限内。

职责：接收网页发来的 base64 文件，依次做四道校验（文件名 / 类型 / 体积 / 写盘），
通过后投一张卡片把落盘路径交给 AI。

为什么不把文件内容投给 AI：
    文件是二进制，AI 看不见也不需要看见。它需要的是路径，
    拿到后自己按需调 read_file（文本类）或告知用户路径（二进制类）。

类型校验复用 read_file 的白名单（file_types.PASTEABLE_EXTS）：
    不在白名单内直接返回错误给网页，不投给 AI——
    否则 AI 会拿到一个读不了的文件、反复尝试后把对话卡住。

调用方是 routes/web.py 的 /api/web/file 视图，本模块不直接注册路由。
"""
import base64
import os
import time

from flask import Blueprint, jsonify, request

import paths
import web_bridge
import app_log
from web_bridge import web_inbox

# 独立蓝图：与 web_source 一致的做法，使 routes/web.py 保持在行数上限内。
# 蓝图名不得与既有重复（web / web_clientlog / web_source）。
bp = Blueprint("web_file", __name__)


def _sanitize_name(raw_name):
    """把对端给的文件名净化成可安全落盘的名字。

    只取基名（去掉任何目录部分），过滤控制字符与 Windows 保留符号，
    避免对端用 ../ 之类的名字写到目录外。
    @param raw_name 原始文件名
    @returns 安全文件名；无法得到合法名字时返回空串
    """
    safe = os.path.basename(str(raw_name or "").replace("\\", "/"))
    # 过滤不可打印字符与文件系统保留符号
    safe = "".join(c for c in safe if c.isprintable() and c not in '<>:"|?*').strip()
    return safe


def _decode_and_check(b64):
    """解码 base64 并校验体积。

    @param b64 base64 字符串
    @returns (raw_bytes, error_response_dict)；成功时 error 为 None
    """
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return None, {"success": False, "error": "bad_base64"}
    # 体积校验：与 QQ 来件同口径，超限直接拒
    from remote_bridge.qq_files import MAX_INBOUND_BYTES
    if len(raw) > MAX_INBOUND_BYTES:
        return None, {
            "success": False,
            "error": "too_large",
            "message": "文件过大（%.1fMB），上限 %.1fMB"
                       % (len(raw) / 1048576.0, MAX_INBOUND_BYTES / 1048576.0),
        }
    return raw, None


def _save(raw, safe_name):
    """把文件内容写入来件目录，返回落盘路径。

    与 QQ 来件共用同一目录，便于统一回收与排查。
    @param raw       文件字节
    @param safe_name 已净化的文件名
    @returns 落盘绝对路径字符串
    """
    paths.QQ_FILES_DIR.mkdir(parents=True, exist_ok=True)
    fname = "web_%d_%s" % (int(time.time() * 1000), safe_name)
    dest = paths.QQ_FILES_DIR / fname
    dest.write_bytes(raw)
    return str(dest)


def handle_upload(data):
    """处理一次网页文件上传（纯逻辑，不依赖 Flask 请求对象）。

    流程：取参 → 净化文件名 → 校验类型 → 解码校验体积 → 落盘 → 投卡片。
    @param data 请求体字典 { name, data(base64), text }
    @returns (响应字典, HTTP 状态码)
    """
    b64 = str(data.get("data") or "")
    if not b64:
        return {"success": False, "error": "empty_file"}, 400

    safe = _sanitize_name(data.get("name"))
    if not safe:
        return {"success": False, "error": "bad_name"}, 400

    # 类型校验前移：不落盘就能判断的先拒掉，省一次写盘
    from file_types import PASTEABLE_EXTS, suffix_of
    ext = suffix_of(safe)
    if ext not in PASTEABLE_EXTS:
        return {
            "success": False,
            "error": "unsupported_type",
            "message": "不支持的文件类型：%s" % (ext or "（无扩展名）"),
        }, 400

    raw, err = _decode_and_check(b64)
    if err:
        return err, 400

    try:
        dest = _save(raw, safe)
    except Exception as e:
        app_log.warn("[web]", "保存网页文件失败：", e)
        return {"success": False, "error": "save_failed: %s" % e}, 500

    # 投卡片：把路径交给 AI，由它自己决定读不读
    card_id = web_bridge.web.ingest_file(
        dest, safe, len(raw), str(data.get("text") or ""))
    return {
        "success": True,
        "cardId": card_id,
        "name": safe,
        "path": dest,
        "size": len(raw),
    }, 200


@bp.route("/api/web/file", methods=["POST", "OPTIONS"])
def web_file():
    """网页发文件：接收 base64 文件，校验后落盘，把路径告诉 AI。

    请求体：{ name: "a.zip", data: base64, text: "" }
    校验与落盘细节见 handle_upload；此处只做请求解析与收件箱记账。
    """
    data = request.get_json(force=True, silent=True) or {}
    result, status = handle_upload(data)
    # 成功才记收件箱：失败时不留半条消息，用户能直接看到错误原因
    if result.get("success"):
        label = (str(data.get("text") or "").strip() or "[文件]") + " " + result.get("name", "")
        web_inbox.append("user", label, kind="web-file", image="")
    return jsonify(**result), status
