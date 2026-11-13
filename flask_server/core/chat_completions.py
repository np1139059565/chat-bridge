"""标准对话接口的内部实现（任务 A-1；A-4 接入标准链路）：消息转换、
待执行调用提取、工具执行、会话存储。

职责边界（见 docs/work-ai-a.md 与 docs/split-mirror-and-tools-service.md）：
- 接收标准 OpenAI 风格 messages / tools，做校验与规范化；
- 调用意图只来自请求侧 assistant.tool_calls（网页 AI 的 bridge-chat-call
  代码块由翻译员翻成标准 tool_calls 送入本接口，规格 3.1 / 4.4）；
  服务端执行后以标准 tool 消息回传，客户端据此续发下一轮请求；
- 工具执行复用 routes/tools.py 的现有管线（内置 -> 自定义 -> 未知），
  不新建执行器，不改 tools/ 下任何文件；
- 服务端不生成 assistant 文本：阶段 2 起占位生成器整体移除（决策 2
  一刀切，不留开关），assistant 轮由模型链路（经翻译员）产生；
- 会话历史按 site_key 落盘（JSON 文件），支持多轮延续。
- model_reply_hook（A-7）：把「history 送真实模型」包装为可注册的分发前钩子
  工厂，与 routes/chat_api.py 的 L10 入口配套；本模块不做网络请求、不持有
  凭证——接真实模型由外部服务负责，代码侧只到入口。

导入风格与 routes/tools.py 一致：flask_server 目录在 sys.path 中，用顶层导入。
注意 conftest.py 提到的双导入路径陷阱（core/ 也在 sys.path）：
测试重定向存储位置时应 monkeypatch 本模块的 _STORE_DIR，
并保证 import 的是同一模块对象（统一顶层 import chat_completions）。
"""

import json
import os
import re
import threading
import uuid
from pathlib import Path

import app_log
import runtime


class ChatAPIError(Exception):
    """可映射为 HTTP 响应的请求侧错误；status 为建议的 HTTP 状态码。"""

    def __init__(self, message, status=400):
        super(ChatAPIError, self).__init__(message)
        self.message = message
        self.status = status


_ALLOWED_ROLES = ("system", "user", "assistant", "tool")

# 会话存储目录：默认为 flask_server/data/chat_sessions（运行时产物目录）。
# 测试里通过 monkeypatch 本变量重定向到临时目录，避免污染真实数据。
_STORE_DIR = None
_SAVE_LOCK = threading.Lock()  # 串行化 replace，避免 Windows 并发 PermissionError


def _store_dir():
    """惰性解析并返回存储目录（自动创建）。"""
    if _STORE_DIR is not None:
        d = Path(_STORE_DIR)
    else:
        d = Path(__file__).resolve().parent.parent / "data" / "chat_sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


_SITE_KEY_RE = re.compile(r"[^A-Za-z0-9_\-]")


def new_site_key():
    return "site_" + uuid.uuid4().hex[:12]


def resolve_site_key(raw):
    """清洗请求携带的 site_key；空返回 None（由调用方生成）。

    含非法字符（字母数字下划线连字符以外）或超长时返回 None，
    由路由层显式报 400，而不是静默替换——对外接口可预期优先。
    """
    s = str(raw or "").strip()
    if not s or len(s) > 64 or _SITE_KEY_RE.search(s):
        return None
    return s


def normalize_messages(messages):
    """校验并规范化标准 messages 数组，返回可安全落盘/回灌的副本。

    规则（docs/split-mirror-and-tools-service.md 决策 5/6/10）：
    - role 只允许 system / user / assistant / tool；
    - content 允许字符串或 null（assistant 带 tool_calls 时可为 null）；
    - assistant 的 tool_calls 原样保留；tool 的 tool_call_id / name 保留。
    不合法抛 ChatAPIError，由路由层转成标准错误响应。
    """
    if not isinstance(messages, list) or not messages:
        raise ChatAPIError("messages 必须是非空数组")
    return [_normalize_item(i, m) for i, m in enumerate(messages)]


def _normalize_item(i, m):
    """校验并规范化单条消息；不合法抛 ChatAPIError（消息带下标定位）。"""
    if not isinstance(m, dict):
        raise ChatAPIError("messages[%d] 必须是对象" % i)
    role = m.get("role")
    if role not in _ALLOWED_ROLES:
        raise ChatAPIError(
            "messages[%d].role 非法：%r（允许：%s）"
            % (i, role, "/".join(_ALLOWED_ROLES))
        )
    content = m.get("content")
    if content is not None and not isinstance(content, str):
        raise ChatAPIError("messages[%d].content 必须是字符串或 null" % i)
    item = {"role": role, "content": content}
    if role == "assistant":
        _merge_assistant_fields(i, m, item)
    elif role == "tool":
        _merge_tool_fields(m, item)
    return item


def _merge_assistant_fields(i, m, item):
    """assistant 的 tool_calls 校验后清洗保留：只留标准字段（5.2 / 6.1）。"""
    tcs = m.get("tool_calls")
    if not tcs:
        return
    if not isinstance(tcs, list):
        raise ChatAPIError("messages[%d].tool_calls 必须是数组" % i)
    item["tool_calls"] = _sanitize_tool_calls(tcs)


def _merge_tool_fields(m, item):
    """tool 的 tool_call_id / name 存在时转字符串保留。"""
    if m.get("tool_call_id"):
        item["tool_call_id"] = str(m["tool_call_id"])
    if m.get("name"):
        item["name"] = str(m["name"])


def _sanitize_tool_calls(tcs):
    """清洗 tool_calls：只保留 id / type / function（name+arguments），丢弃网页场景附加字段。"""
    out = []
    for tc in tcs:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        out.append({"id": tc.get("id"), "type": "function",
                    "function": {"name": fn.get("name"), "arguments": fn.get("arguments")}})
    return out


def _answered_call_ids(messages):
    """收集历史中所有已回填结果的 tool_call_id（str 归一）集合。"""
    return {
        str(m["tool_call_id"])
        for m in messages
        if m.get("role") == "tool" and m.get("tool_call_id")
    }


def _pending_key(tc, answered, seen):
    """归一化调用 id 并判重；应跳过（无 id / 已回填 / 本轮已收）返回 None。"""
    key = str(tc.get("id") or "")
    if key and key not in answered and key not in seen:
        return key
    return None


def pending_tool_calls(messages):
    """收集历史中尚未回填 tool 结果的调用，按提交顺序返回（A-4 标准链路）。

    调用意图只来自请求侧 assistant.tool_calls；防重放以 tool_call_id 配对：
    已回填结果的调用不再重复执行，客户端重发全量历史天然幂等；
    同一 id 多次声明以首次为准；无 id 的调用无法与 tool 结果配对，
    跳过——无法定位结果的调用不该执行，否则每轮都会重放。
    """
    answered = _answered_call_ids(messages)
    out = []
    seen = set()
    for m in messages:
        if m.get("role") != "assistant":
            continue
        for tc in m.get("tool_calls") or ():
            if not isinstance(tc, dict):
                continue
            key = _pending_key(tc, answered, seen)
            if key:
                seen.add(key)
                out.append(tc)
    return out


def _response_to_body(resp):
    """把管线函数的返回值归一成 dict（兼容 Response 与 (Response, status) 元组）。"""
    if isinstance(resp, tuple):
        resp = resp[0]
    if hasattr(resp, "get_json"):
        return resp.get_json(silent=True)
    if isinstance(resp, dict):
        return resp
    return None


def _param_error(name, message):
    """参数类失败信封（errorType=ToolParamError，origin=parameter）。"""
    return {
        "success": False,
        "tool": name,
        "error": message,
        "errorType": "ToolParamError",
        "origin": "parameter",
    }


def _exec_error(name, message):
    """执行类失败信封（errorType=ToolExecError，origin=executor）。"""
    return {
        "success": False,
        "tool": name,
        "error": message,
        "errorType": "ToolExecError",
        "origin": "executor",
    }


def _parse_call_params(name, raw_args):
    """把 arguments 解析为参数 dict；返回 (params, err)，err 非空即失败信封。"""
    if raw_args is None or str(raw_args).strip() == "":
        return {}, None
    try:
        params = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except Exception:
        return None, _param_error(name, "tool_calls 的 arguments 不是合法 JSON：%r" % (raw_args,))
    if not isinstance(params, dict):
        return None, _param_error(name, "tool_calls 的 arguments 必须是 JSON 对象")
    return params, None


def _dispatch_tool(name, params):
    """按「内置 -> 自定义 -> 未知」顺序走现有执行管线，返回信封 dict。

    管线自身的意外异常在这里兜成执行失败信封，不外抛、不产生 500。
    """
    import custom_tools
    import routes.tools as rt

    try:
        if name in runtime.DISPATCH:
            return _response_to_body(rt._call_builtin(name, params))
        if custom_tools.get_tool(name):
            return _response_to_body(rt._call_custom(name, params, "", ""))
        return _response_to_body(rt._unknown_tool(name))
    except Exception as e:  # noqa: BLE001 - 信封兜底是本函数的职责
        return _exec_error(name, str(e))


def execute_tool_call(call):
    """执行一个 tool_call：完整复用 routes/tools.py 的现有管线。

    - 内置工具走 _call_builtin（启用检查、参数校验、60s 超时、体积兜底）；
    - 自定义工具走 _call_custom（标准对话接口没有页面上下文，
      page_url / host_page_url 传空串）；
    - 未知工具走 _unknown_tool（404 信封，含 available 清单）。
    返回统一为信封 dict；工具失败时信封含 errorType / origin / hint，
    由调用方 JSON 字符串化后放进 tool 角色 content（实现原则 2、决策 10）。
    """
    fn = call.get("function") or {}
    name = str(fn.get("name") or "").strip()
    params, err = _parse_call_params(name, fn.get("arguments"))
    if err:
        return err
    body = _dispatch_tool(name, params)
    if isinstance(body, dict):
        return body
    return _exec_error(name, "工具返回了非结构化结果")


def tool_message_from_call(call, body):
    """把工具执行结果包成标准 tool 角色消息。

    content 是整套结果信封的 JSON 字符串（决策 10）：
    成功含 success/result，失败含 error/errorType/origin/hint，
    不加额外布尔字段。
    """
    fn = call.get("function") or {}
    return {
        "role": "tool",
        "tool_call_id": str(call.get("id") or ""),
        "name": str(fn.get("name") or ""),
        "content": json.dumps(body, ensure_ascii=False),
    }


def merge_history(stored, incoming):
    """以服务端已存历史为权威，合并本轮请求消息，返回合并后的完整序列。

    - stored 为空：以 incoming 重建；
    - incoming 与 stored 前缀一致（客户端传全量）：只追加新增；
    - incoming 是 stored 的真前缀（重发已存内容）：幂等返回 stored；
    - incoming 恰为 stored 尾部片段（重复发送已存内容）：不重复追加；
    - incoming 首条是新 user（只传增量）：追加到既有历史后（场景 4）；
    - 其余（真分叉）：以 incoming 重建。
    """
    if not stored:
        return list(incoming)
    overlap = _common_prefix_len(stored, incoming)
    if overlap >= len(stored):
        return list(stored) + list(incoming[overlap:])
    if overlap >= len(incoming):
        return list(stored)
    if _is_tail_repeat(stored, incoming):
        return list(stored)
    if incoming and incoming[0].get("role") == "user":
        return list(stored) + list(incoming)
    return list(incoming)


def _common_prefix_len(stored, incoming):
    """两序列从头逐位比较，返回一致的最长前缀长度。"""
    overlap = 0
    for a, b in zip(stored, incoming):
        if a != b:
            break
        overlap += 1
    return overlap


def _is_tail_repeat(stored, incoming):
    """incoming 恰为 stored 的尾部片段（重复发送已存内容）时为真。"""
    return (
        bool(incoming)
        and len(incoming) <= len(stored)
        and stored[-len(incoming):] == incoming
    )


def _as_assistant_reply(fetcher, reply):
    """把 fetcher 返回值规范化为 assistant 消息 dict；None 原样返回。

    str 视为模型文本回复，包装为 {role: assistant, content: str}；
    dict 校验 role 必须是 assistant；其它类型是契约违约，抛 TypeError。
    """
    if reply is None:
        return None
    if isinstance(reply, str):
        reply = {"role": "assistant", "content": reply}
    if not isinstance(reply, dict):
        raise TypeError(
            "model fetcher %r 返回 %s：契约要求 None、str 或 dict"
            % (getattr(fetcher, "__name__", fetcher), type(reply).__name__))
    if reply.get("role") != "assistant":
        raise TypeError(
            "模型回复的 role 必须是 assistant，实际 %r" % reply.get("role"))
    return reply


def model_reply_hook(fetch_model_reply):
    """把「history 送真实模型」包装为 L10 分发前钩子（A-7）。

    用法（接真实模型的一方装配时注册，凭证由外部服务持有）：

        register_pre_dispatch_hook(model_reply_hook(fetch_reply))

    fetch_reply(history) 契约：入参是合并后完整消息快照（只读）；返回
    None / str / dict（assistant 轮，可带 tool_calls——模型声明的调用
    意图交服务端标准管线执行）；违约或 fetcher 自身异常都让请求失败且
    无部分副作用（不执行工具、不落盘）。

    模型回复经 _normalize_item 规范化追加到 history 尾部，分发、落盘、
    回声同步生效（网页附加字段随规范化清洗）。本函数不做网络请求、
    不读凭证——接真实模型是外部服务的事，代码侧只到入口（A-7 边界）。
    """

    def hook(history):
        reply = _as_assistant_reply(
            fetch_model_reply, fetch_model_reply(history))
        if reply is None:
            return None
        return list(history) + [_normalize_item(len(history), reply)]

    return hook

def load_session(site_key):
    """读取会话历史；损坏（非法 JSON / 非列表）时备份原文件并记日志，
    返回 [] 重新累积——历史不静默丢失，接口不中断（A-3 健壮性）。"""
    fp = _store_dir() / (site_key + ".json")
    if not fp.is_file():
        return []
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 - 读取异常统一走备份兜底
        _backup_broken(site_key, fp, repr(e))
        return []
    if not isinstance(data, list):
        _backup_broken(site_key, fp, "顶层不是列表")
        return []
    return data


def _backup_broken(site_key, fp, why):
    """损坏会话文件的诊断兜底：改名 .bad 保留 + 告警日志，不中断接口。"""
    backup = fp.with_name(fp.name + ".bad")
    try:
        os.replace(str(fp), str(backup))
    except OSError as e:
        app_log.warn("[chat][sessions]", "损坏文件备份失败", "site_key=" + site_key, repr(e))
        return
    app_log.warn("[chat][sessions]", "会话文件损坏，已备份为", backup.name,
                 "site_key=" + site_key, "原因=" + why)


def save_session(site_key, messages):
    """原子落盘（唯一临时文件 + 串行 replace），返回存储文件路径。"""
    fp = _store_dir() / (site_key + ".json")
    # 唯一临时文件名 + replace 串行化：并发写不互相覆盖
    tmp = fp.with_name("%s.%s.tmp" % (fp.name, uuid.uuid4().hex))
    try:
        tmp.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")
        with _SAVE_LOCK:
            os.replace(str(tmp), str(fp))
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return str(fp)
