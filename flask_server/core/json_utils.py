"""JSON 处理公共原语 —— 安全反序列化

职责：把「安全反序列化 JSON 文本」这段被多处重复的逻辑集中一处，
供记忆子系统各模块共用，避免同一实现多处维护。

设计要点：
- 空文本直接返回默认值，不抛异常；
- 解析失败（非合法 JSON）也返回默认值，不抛异常；
- 默认值由调用方传入，便于各场景给出合适兜底（如 {} / []）。

依赖：json
"""
import json


def safe_json_loads(text, default):
    """安全反序列化 JSON 文本：空值或非法 JSON 时返回默认值。

    @param text    待解析的 JSON 文本；为空（None / 空串）时直接返回 default
    @param default 解析失败或文本为空时的兜底返回值
    @returns 解析结果；无法解析时返回 default
    """
    # 空文本：无需解析，直接兜底（避免 json.loads(None) 抛异常）
    if not text:
        return default
    try:
        # 正常解析
        return json.loads(text)
    except Exception:
        # 非法 JSON：按约定返回兜底，不向上抛
        return default
