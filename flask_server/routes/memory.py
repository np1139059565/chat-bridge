"""AI 工具调用镜像插件 —— 工作记忆目录指纹

职责：提供 memory 目录的内容指纹（文件名 + 内容一起算 md5），
供前端判断 AI 是否真的写入了工作记忆。

为什么用指纹而不是「参数里是否出现 memory 路径」：
- 只看参数会把「读取」误判为「写入」；
- AI 可能用变量拼接路径，字符串匹配防不住。
指纹反映目录内容的真实变化，读不改变内容、写必改变内容，
因此能准确区分二者，且不受路径书写方式影响。
"""
import hashlib

from flask import Blueprint, jsonify

import paths

bp = Blueprint("memory", __name__)


def memory_fingerprint():
    """计算 memory 目录的内容指纹。

    遍历目录下所有文件，按相对路径排序后，把「文件名 + 文件内容」
    依次喂给同一个 md5。目录不存在或为空时返回空串。
    """
    if not paths.MEMORY_DIR.is_dir():
        return ""
    h = hashlib.md5()
    # 排序保证遍历顺序稳定：顺序不同会算出不同指纹，造成误判
    files = sorted(f for f in paths.MEMORY_DIR.rglob("*") if f.is_file())
    for f in files:
        # 文件名参与：新增空文件也算变化
        h.update(str(f.relative_to(paths.MEMORY_DIR)).replace("\\", "/").encode("utf-8"))
        try:
            h.update(f.read_bytes())
        except Exception:
            # 单个文件读失败不阻断整体：跳过其内容，仍以文件名为准
            pass
    return h.hexdigest()


@bp.route("/memory/fingerprint", methods=["GET"])
def get_fingerprint():
    """返回 memory 目录当前指纹，供前端对比是否发生写入。"""
    return jsonify({"success": True, "fingerprint": memory_fingerprint()})
