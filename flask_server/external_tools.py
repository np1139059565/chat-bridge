"""外部工具提供方注册与转发。

提供方来自 skill 声明（tool.json 中的 provider 字段）。
提供方通过 /api/ext/<provider> 轮询拉取命令并回传结果。

本模块维护：
    1. 提供方在线状态（按最近一次 poll 时间判定）
    2. 各提供方的待执行命令队列
    3. 挂起中的工具调用（按 request_id 唤醒）
"""
import threading
import time
import uuid

# 提供方在线判定窗口（秒）
ONLINE_WINDOW = 3.0

# 单个工具调用的转发超时（秒）
FORWARD_TIMEOUT = 60.0


class ProviderHub:
    """提供方状态、命令队列与结果等待。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_poll = {}        # provider -> 最近 poll 时间戳
        self._queues = {}           # provider -> [command, ...]
        self._events = {}           # request_id -> threading.Event
        self._results = {}          # request_id -> result
        self._providers = {}        # provider -> 工具定义列表

    # ---------- 提供方与工具定义 ----------
    def register_provider(self, provider, tools):
        """登记（或覆盖）某提供方的工具定义列表。"""
        with self._lock:
            self._providers[provider] = list(tools or [])

    def replace_providers(self, groups):
        """用最新分组整体替换提供方定义；不在分组内的提供方被移除。

        保证工具下线后立即从工具列表消失。
        """
        with self._lock:
            self._providers = {k: list(v or []) for k, v in (groups or {}).items()}

    def provider_tools(self):
        """返回所有【在线】提供方的工具定义合并列表。"""
        now = time.time()
        out = []
        with self._lock:
            for provider, tools in self._providers.items():
                last = self._last_poll.get(provider, 0)
                if now - last <= ONLINE_WINDOW:
                    out.extend(tools)
        return out

    def is_online(self, provider):
        with self._lock:
            last = self._last_poll.get(provider, 0)
        return (time.time() - last) <= ONLINE_WINDOW

    def find_tool(self, name):
        """按工具名查其所属提供方与定义。返回 (provider, tool) 或 (None, None)。"""
        with self._lock:
            for provider, tools in self._providers.items():
                for t in tools:
                    if t.get("name") == name:
                        return provider, t
        return None, None

    # ---------- 轮询与命令队列 ----------
    def poll(self, provider):
        """记录心跳并取走该提供方的待执行命令。"""
        with self._lock:
            self._last_poll[provider] = time.time()
            commands = self._queues.get(provider, [])
            self._queues[provider] = []
        return commands

    def push_command(self, provider, command):
        with self._lock:
            self._queues.setdefault(provider, []).append(command)

    # ---------- 工具调用转发与等待 ----------
    def dispatch(self, provider, tool, params, silent=False):
        """把一次工具调用入队。

        silent=False：阻塞等待结果，返回 (ok, data_or_error)。
        silent=True ：一次性副作用工具，仅入队即返回，不等待结果。
        """
        request_id = str(uuid.uuid4())
        command = {
            "request_id": request_id,
            "tool": tool,
            "params": params or {},
            "silent": bool(silent),
        }
        if silent:
            # 副作用类工具：入队即结束，不占用等待线程，也不产生回传结果
            self.push_command(provider, command)
            return True, {"dispatched": True, "silent": True}
        event = threading.Event()
        with self._lock:
            self._events[request_id] = event
        self.push_command(provider, command)
        if not event.wait(timeout=FORWARD_TIMEOUT):
            with self._lock:
                self._events.pop(request_id, None)
            return False, "FORWARD_TIMEOUT"
        with self._lock:
            result = self._results.pop(request_id, None)
        return True, result

    def resolve(self, request_id, result):
        """回传某次工具调用的结果，唤醒等待方。"""
        with self._lock:
            event = self._events.pop(request_id, None)
            if event:
                self._results[request_id] = result
        if event:
            event.set()
            return True
        return False


# 全局单例
hub = ProviderHub()
