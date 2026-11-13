"""标准对话接口（任务 A-1；A-4 接入标准链路）：POST /v1/chat/completions。

职责：
- 接收标准 OpenAI 风格请求体（messages / tools / site_key / model / stream）；
- stream=true 时明确拒绝（HTTP 400，不静默降级，验收场景 5）；
- 调 core/chat_completions.py 完成校验、历史合并与工具执行（完整复用
  routes/tools.py 现有管线）；
- 调用意图只来自请求侧 assistant.tool_calls（翻译员把网页 AI 的
  bridge-chat-call 代码块翻译而来，规格 3.1 / 4.4）：服务端执行历史中
  尚未回填结果的调用，以标准 tool 消息回传；服务端不生成 assistant
  文本（阶段 2 起占位生成器移除，决策 2）；
- 返回标准 choices 结构，并附 site_key / messages 扩展字段：
  messages 是本轮合并后的完整消息序列（含 tool 结果），供客户端
  断言与续接（docs/split-mirror-and-tools-service.md 决策 14）。

本文件不实现任何工具执行逻辑，不修改 tools/ 与 routes/tools.py。
 - L10 契约入口：register_pre_dispatch_hook（工具分发前的可插拔钩子，契约见下方注释）。
"""

import threading
import time
import uuid

from flask import Blueprint, current_app, jsonify, request

import chat_completions as cc

# ---- L10 契约入口（A-5 新增）：标准链路的可插拔前置钩子 ----
# 边界（docs/work-ai-a.md A-5）：只新增入口与契约测试，不改既有链路语义、
# 不建切换开关、不引入 asyncio 依赖、不碰 remote_bridge / extend / tools。
# 唯一固定点位：历史合并之后、待执行调用分发（_execute_pending）之前。
_PRE_DISPATCH_HOOKS = []
_HOOKS_LOCK = threading.Lock()


def register_pre_dispatch_hook(fn):
    """注册分发前钩子（L10 契约入口）；返回 fn，支持装饰器用法。

    契约：
    - fn(history) 同步调用一次；history 是合并后的完整消息 list[dict]，
      视为只读入参（需要改动时返回新 list，不要原地改写）；
    - 返回 None：沿用原 history；返回 list：整体替换后续各步
      （分发输入、落盘、响应 choices/messages）使用的 history；
    - 多个钩子按注册顺序链式执行：前一钩子的返回值是下一钩子的入参；
    - 返回 None/list 以外的类型视为契约违约，抛 TypeError；
      钩子内部异常不被本层捕获，沿请求向上抛（钩子作者自负健壮性）；
    - 注册与清空线程安全；单次请求迭代用的是调用时点的注册快照。
    """
    with _HOOKS_LOCK:
        _PRE_DISPATCH_HOOKS.append(fn)
    return fn


def clear_pre_dispatch_hooks():
    """清空全部已注册钩子（供测试隔离；业务代码不应调用）。"""
    with _HOOKS_LOCK:
        _PRE_DISPATCH_HOOKS.clear()


def _run_pre_dispatch_hooks(history):
    """按注册顺序执行钩子，返回最终生效的 history。"""
    with _HOOKS_LOCK:
        hooks = list(_PRE_DISPATCH_HOOKS)
    for fn in hooks:
        out = fn(history)
        if out is None:
            continue
        if not isinstance(out, list):
            raise TypeError(
                "pre-dispatch hook %r 返回 %s：契约要求 None 或 list"
                % (getattr(fn, "__name__", fn), type(out).__name__),
            )
        history = out
    return history


# 「history 送真实模型」的装配式用法（A-7，工厂见 core 层）：
#     register_pre_dispatch_hook(cc.model_reply_hook(fetch_reply))
# fetch_reply 由持有外部模型服务与凭证的一方提供；本路由不读配置、
# 不建切换开关、不硬编码凭证。

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


def _validate_tools(payload):
    """tools 声明只做类型校验；服务端是低层执行器，不据其过滤执行（规格 3.9）。"""
    tools = payload.get("tools")
    if tools is None:
        return
    if not isinstance(tools, list):
        raise InvalidChatRequest("tools 必须是数组")


def _resolve_session_key(payload):
    """解析 site_key：携带且非法时报错；缺省时生成新键并沿用。"""
    raw_key = payload.get("site_key")
    site_key = cc.resolve_site_key(raw_key)
    if raw_key and site_key is None:
        raise InvalidChatRequest(
            "site_key 非法：仅允许字母、数字、下划线、连字符，长度 1-64。"
        )
    return site_key or cc.new_site_key()


def _execute_pending(history):
    """执行历史中尚未回填结果的调用，返回本轮新增消息（tool 结果序列）。

    防重放由 cc.pending_tool_calls 按 tool_call_id 配对完成：已回填的
    调用不再执行，重发全量历史天然幂等；并行多调用逐个执行、按序回传。
    """
    round_messages = []
    for call in cc.pending_tool_calls(history):
        body = cc.execute_tool_call(call)
        round_messages.append(cc.tool_message_from_call(call, body))
    return round_messages


def _save_history(site_key, final_history):
    """落盘会话历史；失败仅告警，不影响本次响应。"""
    try:
        cc.save_session(site_key, final_history)
    except Exception as e:  # noqa: BLE001 - 落盘失败不影响本次响应
        current_app.logger.warning(
            "chat_api: 会话落盘失败 site_key=%s: %s", site_key, e
        )


def _echo_message(final_history):
    """choices.message 回传合并历史最后一条 assistant 消息（标准链路回声）。

    标准链路里 assistant 消息由客户端产生并送入；这里回声末条，客户端
    无需自行回查。历史里没有 assistant（纯 system/user 开局）时给一条
    空文本 assistant 结构占位回声——只进响应、不落盘（保持历史纯标准）。
    """
    for m in reversed(final_history):
        if m.get("role") == "assistant":
            return m
    return {"role": "assistant", "content": ""}


def _build_response(payload, round_messages, final_history, site_key):
    """组装标准 choices 响应（usage 粗估 + site_key / messages 扩展字段）。"""
    prompt_chars = sum(len(m.get("content") or "") for m in final_history)
    completion_chars = sum(len(m.get("content") or "") for m in round_messages)
    finish_reason = "tool_calls" if round_messages else "stop"
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex[:24],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.get("model") or "chat-bridge",
        "choices": [
            {
                "index": 0,
                "message": _echo_message(final_history),
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
    """POST /v1/chat/completions：校验 -> 合并历史 -> 执行待执行调用 -> 落盘 -> 响应。"""
    try:
        payload = _parse_payload()
        incoming = cc.normalize_messages(payload.get("messages"))
        _validate_tools(payload)
        site_key = _resolve_session_key(payload)
    except cc.ChatAPIError as e:
        return jsonify(_error_body(e.message)), e.status
    except InvalidChatRequest as e:
        return jsonify(_error_body(e.message, code=e.code)), 400

    history = cc.merge_history(cc.load_session(site_key), incoming)
    history = _run_pre_dispatch_hooks(history)
    round_messages = _execute_pending(history)

    final_history = history + round_messages
    _save_history(site_key, final_history)
    return jsonify(
        _build_response(payload, round_messages, final_history, site_key)
    )
