"""标准对话接口的内部实现（任务 A-1）：消息转换、占位生成、会话存储。

职责边界（见 docs/work-ai-a.md 与 docs/split-mirror-and-tools-service.md）：
- 接收标准 OpenAI 风格 messages / tools，做校验与规范化；
- 工具执行复用 routes/tools.py 的现有管线（内置 -> 自定义 -> 未知），
  不新建执行器，不改 tools/ 下任何文件；
- 阶段一未接真实模型，assistant 轮由占位生成器按可解释规则产生，
  阶段 2 接入翻译员后只需替换 generate_reply；
- 会话历史按 site_key 落盘（JSON 文件），支持多轮延续。

导入风格与 routes/tools.py 一致：flask_server 目录在 sys.path 中，用顶层导入。
注意 conftest.py 提到的双导入路径陷阱（core/ 也在 sys.path）：
测试重定向存储位置时应 monkeypatch 本模块的 _STORE_DIR，
并保证 import 的是同一模块对象（统一顶层 import chat_completions）。
"""

import json
import os
import re
import uuid
from pathlib import Path

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
    """assistant 的 tool_calls 原样保留（携带时校验为数组）。"""
    tcs = m.get("tool_calls")
    if not tcs:
        return
    if not isinstance(tcs, list):
        raise ChatAPIError("messages[%d].tool_calls 必须是数组" % i)
    item["tool_calls"] = tcs


def _merge_tool_fields(m, item):
    """tool 的 tool_call_id / name 存在时转字符串保留。"""
    if m.get("tool_call_id"):
        item["tool_call_id"] = str(m["tool_call_id"])
    if m.get("name"):
        item["name"] = str(m["name"])


def declared_tool_names(tools):
    """从标准 tools 声明里提取工具名列表。

    本任务原样接收外部传入的标准 JSON Schema（容器是对象、必填是顶层数组），
    不依赖阶段 1b 的内部声明改造；这里只读 name 用于占位判定。
    """
    names = []
    if not isinstance(tools, list):
        return names
    for t in tools:
        if not isinstance(t, dict):
            continue
        fn = t.get("function")
        if isinstance(fn, dict) and fn.get("name"):
            names.append(str(fn["name"]))
        elif t.get("name"):
            names.append(str(t["name"]))
    return names


# 占位生成器：识别「工具名({...})」形式的显式参数表达，其余按空参数处理
_CALL_ARGS_RE = re.compile(r"([A-Za-z0-9_\-]+)\s*[\(（]\s*(\{.*?\})\s*[\)）]", re.S)


def generate_reply(messages, tool_names):
    """阶段一占位生成：决定本轮 assistant 消息（文本或 tool_calls）。

    规则（可解释、无外部依赖，阶段 2 由真实模型替换）：
    - 上一条消息是 tool 结果：直接出文本（工具刚执行完，该出文本了，
      同时避免占位器对同一工具反复触发）；
    - tools 非空且最近一条 user 文本中出现某声明工具名：返回含
      tool_calls 的 assistant；文本里有 名字({...}) 时解析其中的 JSON
      对象作 arguments，否则空参数 "{}"（不合法参数会走工具的参数错误
      信封，正好覆盖验收场景 6）；
    - 防重放：该 user 文本之后若已存在针对同一工具的 tool_calls
      assistant（客户端在重发历史），视为重放，直接出文本；
    - 其余：纯文本占位回复，不含 tool_calls。
    """
    if messages and messages[-1].get("role") == "tool":
        return _text_reply("已收到工具结果并继续生成下一轮（阶段一未接入真实模型）。")
    user_text = _last_user_text(messages)
    picked = _pick_tool(user_text, tool_names) if tool_names and user_text else None
    if picked is None:
        return _text_reply(
            "已收到 %d 条消息（阶段一未接入真实模型，此回复由服务端占位生成器产生）。"
            % len(messages)
        )
    start = _last_user_index(messages, user_text)
    if picked in _called_tools_after(messages, start):
        return _text_reply("该工具已执行过，结果见历史中的 tool 消息（阶段一占位生成器）。")
    return _tool_call_reply(picked, _parse_call_args(user_text, picked))


def _text_reply(text):
    """构造纯文本 assistant 占位回复。"""
    return {"role": "assistant", "content": "[占位回复] " + text}


def _last_user_text(messages):
    """最近一条带内容的 user 文本；无则返回空串。"""
    for m in reversed(messages):
        if m.get("role") == "user" and m.get("content"):
            return m["content"]
    return ""


def _pick_tool(user_text, tool_names):
    """返回 user 文本中出现的第一个已声明工具名；无则 None。"""
    for name in tool_names:
        if name in user_text:
            return name
    return None


def _last_user_index(messages, user_text):
    """定位该 user 文本最后一次出现的位置，返回其后第一条的下标。"""
    start = 0
    for i, m in enumerate(messages):
        if m.get("role") == "user" and m.get("content") == user_text:
            start = i + 1
    return start


def _called_tools_after(messages, start):
    """收集 messages[start:] 中 assistant 已通过 tool_calls 调过的工具名。"""
    names = set()
    for m in messages[start:]:
        if m.get("role") != "assistant":
            continue
        for tc in m.get("tool_calls") or ():
            fn = tc.get("function") or {}
            if fn.get("name"):
                names.add(fn["name"])
    return names


def _parse_call_args(user_text, picked):
    """解析「工具名({...})」显式参数中的 JSON 对象；无或非法返回 "{}"。"""
    m = _CALL_ARGS_RE.search(user_text)
    if not m or m.group(1) != picked:
        return "{}"
    try:
        parsed = json.loads(m.group(2))
    except Exception:
        return "{}"
    if isinstance(parsed, dict):
        return json.dumps(parsed, ensure_ascii=False)
    return "{}"


def _tool_call_reply(picked, args_json):
    """构造含 tool_calls 的 assistant 占位回复（单工具调用）。"""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_" + uuid.uuid4().hex[:12],
                "type": "function",
                "function": {"name": picked, "arguments": args_json},
            }
        ],
    }


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


def load_session(site_key):
    """读取某 site_key 的会话历史；不存在或损坏时返回空列表。"""
    fp = _store_dir() / (site_key + ".json")
    if not fp.is_file():
        return []
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save_session(site_key, messages):
    """原子落盘（tmp + replace），返回存储文件路径字符串。"""
    fp = _store_dir() / (site_key + ".json")
    tmp = fp.with_name(fp.name + ".tmp")
    tmp.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(fp))
    return str(fp)