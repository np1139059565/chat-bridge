"""标准对话接口（任务 A-1）：POST /v1/chat/completions。

职责：
- 接收标准 OpenAI 风格请求体（messages / tools / site_key / model / stream）；
- stream=true 时明确拒绝（HTTP 400，不静默降级，验收场景 5）；
- 调 core/chat_completions.py 完成校验、占位生成、工具执行（完整复用
  routes/tools.py 现有管线）、历史合并与落盘；
- 返回标准 choices 结构，并附 site_key / messages 扩展字段：
  messages 是本轮合并后的完整消息序列（含 tool 结果），供客户端
  断言与续接（docs/split-mirror-and-tools-service.md 决策 14）。

本文件不实现任何工具执行逻辑，不修改 tools/ 与 routes/tools.py。
"""

import time
import uuid

from flask import Blueprint, current_app, jsonify, request

import chat_completions as cc

bp = Blueprint("chat_api", __name__)


class InvalidChatRequest(Exception):
    """路由层请求侧错误：message + 可选 code，统一转 400 错误响应。"""

    def __init__(self, message, code=None):
        super(InvalidChatRequest, self).__init__(message)
        self.message = message
        self.code = code


def _error_body(message, err_type="invalid_request_error", code=None):
    """标准错误响应体（OpenAI 风格）。"""
    err = {"message": message, "type": err_type}
    if code:
        err["code"] = code
    return {"error": err}


def _parse_payload():
    """读取请求体；非 JSON 对象或 stream=true 时报错（场景 5：不静默降级）。"""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise InvalidChatRequest("请求体必须是 JSON 对象")
    if payload.get("stream"):
        raise InvalidChatRequest(
            "本服务暂不支持流式输出：请省略 stream 或传 stream=false。",
            code="stream_not_supported",
        )
    return payload


def _parse_tool_names(payload):
    """提取并校验 tools 声明，返回其中的工具名列表。"""
    tools = payload.get("tools")
    if tools is None:
        tools = []
    if not isinstance(tools, list):
        raise InvalidChatRequest("tools 必须是数组")
    return cc.declared_tool_names(tools)


def _resolve_session_key(payload):
    """解析 site_key：携带且非法时报错；缺省时生成新键并沿用。"""
    raw_key = payload.get("site_key")
    site_key = cc.resolve_site_key(raw_key)
    if raw_key and site_key is None:
        raise InvalidChatRequest(
            "site_key 非法：仅允许字母、数字、下划线、连字符，长度 1-64。"
        )
    return site_key or cc.new_site_key()


def _run_tool_round(history, reply, tool_names):
    """执行 reply 的 tool_calls 并续写下一轮文本，返回本轮全部消息。"""
    round_messages = [reply]
    for call in reply["tool_calls"]:
        body = cc.execute_tool_call(call)
        round_messages.append(cc.tool_message_from_call(call, body))
    # 工具刚执行完：续写下一轮文本回复
    # （占位生成器遇 tool 结尾出文本，不会再次触发工具）。
    round_messages.append(cc.generate_reply(history + round_messages, tool_names))
    return round_messages


def _save_history(site_key, final_history):
    """落盘会话历史；失败仅告警，不影响本次响应。"""
    try:
        cc.save_session(site_key, final_history)
    except Exception as e:  # noqa: BLE001 - 落盘失败不影响本次响应
        current_app.logger.warning(
            "chat_api: 会话落盘失败 site_key=%s: %s", site_key, e
        )


def _build_response(payload, reply, round_messages, final_history, site_key):
    """组装标准 choices 响应（usage 粗估 + site_key / messages 扩展字段）。"""
    prompt_chars = sum(len(m.get("content") or "") for m in final_history)
    completion_chars = sum(len(m.get("content") or "") for m in round_messages)
    finish_reason = "tool_calls" if reply.get("tool_calls") else "stop"
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex[:24],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.get("model") or "chat-bridge-placeholder",
        "choices": [
            {
                "index": 0,
                "message": reply,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": prompt_chars // 4,
            "completion_tokens": completion_chars // 4,
            "total_tokens": (prompt_chars + completion_chars) // 4,
        },
        # 扩展字段（决策 14：标准结构之上附加信息）
        "site_key": site_key,
        "messages": final_history,
    }


@bp.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    """POST /v1/chat/completions：校验 -> 合并历史 -> 占位生成 -> 落盘 -> 响应。"""
    try:
        payload = _parse_payload()
        incoming = cc.normalize_messages(payload.get("messages"))
        tool_names = _parse_tool_names(payload)
        site_key = _resolve_session_key(payload)
    except cc.ChatAPIError as e:
        return jsonify(_error_body(e.message)), e.status
    except InvalidChatRequest as e:
        return jsonify(_error_body(e.message, code=e.code)), 400

    history = cc.merge_history(cc.load_session(site_key), incoming)
    reply = cc.generate_reply(history, tool_names)

    round_messages = [reply]
    if reply.get("tool_calls"):
        # 服务端经现有链路执行工具（实现原则 1），
        # 结果信封 JSON 化入 tool 消息（实现原则 2、决策 10）。
        round_messages = _run_tool_round(history, reply, tool_names)

    final_history = history + round_messages
    _save_history(site_key, final_history)
    return jsonify(
        _build_response(payload, reply, round_messages, final_history, site_key)
    )