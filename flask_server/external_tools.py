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


def log(*args):
    """打印外部工具路由日志（统一前缀，便于在服务端控制台过滤）。

    这些日志用于判断「命令是否被正确的页面取走」：入队记一次、
    取走时记一次归属决策，双开时命令串页能据此直接定位。
    """
    print("[ext]", *args)

# 提供方在线判定窗口（秒）：仅用于「已连接」指示灯展示，不参与执行判断
ONLINE_WINDOW = 10.0

# 单个工具调用的等待上限（秒）：请求入队后等待提供方取走的保险丝，
# 防止提供方始终不来取时调用方无限期挂起。
FORWARD_TIMEOUT = 10.0

# 「工具已打开」的有效期（秒）：扩展每次轮询都上报自己的工具（抽屉）是否打开，
# 打开则登记、关闭则注销。命令只认「目标页面的工具当前处于打开状态」；
# 目标页面的工具没打开，命令立即允许其他页面代收，不再等待时间窗。
# 该窗口仅用于清理「页面崩溃 / 直接关闭标签页，来不及注销」的僵尸登记。
# 取值须大于扩展的常规轮询间隔（5 秒），避免正常页面被误清。
OPEN_WINDOW = 15.0


def normalize_url(url):
    """规整页面地址，供「命令目标页面」与「轮询页面」比对。

    两侧地址都来自浏览器的 location.href，但可能因 hash、尾斜杠差异
    导致字符串不相等，这里统一去掉 hash 与尾部斜杠再比较。
    @param url 原始页面地址
    @returns 规整后的地址；空输入返回空串
    """
    if not url:
        return ""
    u = str(url).strip()
    h = u.find("#")           # 去掉 hash：同一文档的不同锚点属于同一页面
    if h != -1:
        u = u[:h]
    while u.endswith("/"):    # 去掉尾部斜杠：/a 与 /a/ 视为同一页面
        u = u[:-1]
    return u


class ProviderHub:
    """提供方状态、命令队列与结果等待。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_poll = {}        # provider -> 最近 poll 时间戳
        self._queues = {}           # provider -> [command, ...]
        self._events = {}           # request_id -> threading.Event
        self._results = {}          # request_id -> result
        self._providers = {}        # provider -> 工具定义列表
        self._open_pages = {}       # provider -> {规整页面地址: 最近上报为打开的时刻}
                                    # 记录「工具（抽屉）当前处于打开状态」的页面，
                                    # 命令据此定向：目标页面的工具没打开就直接逸散。

    # ---------- 工具打开状态登记 ----------
    def set_page_open(self, provider, page_url, is_open):
        """登记 / 注销某页面的「工具已打开」状态。

        扩展每次轮询都上报工具（抽屉）是否打开：打开则登记，关闭则注销。
        命令队列据此判断目标页面此刻能否消费命令。
        @param provider 提供方标识
        @param page_url 页面地址
        @param is_open 工具是否打开
        """
        target = normalize_url(page_url)
        if not target:
            return
        with self._lock:
            pages = self._open_pages.setdefault(provider, {})
            if is_open:
                pages[target] = time.time()
            else:
                pages.pop(target, None)

    def is_page_open(self, provider, page_url):
        """判断某页面的工具当前是否打开。

        除显式登记外，还用 OPEN_WINDOW 清理僵尸登记：页面崩溃或标签被直接
        关闭时来不及注销，超期即视为已关闭，避免命令永远等一个不会来的页面。
        @param provider 提供方标识
        @param page_url 页面地址
        @returns 是否打开
        """
        target = normalize_url(page_url)
        if not target:
            return False
        with self._lock:
            pages = self._open_pages.get(provider, {})
            ts = pages.get(target)
            if ts is None:
                return False
            if (time.time() - ts) > OPEN_WINDOW:
                # 超期未续报：判定为僵尸登记，顺手清掉
                pages.pop(target, None)
                return False
            return True

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
        """返回所有已注册提供方的工具定义合并列表。

        在线状态仅用于界面提示，不影响工具是否可被调用：只要工具已注册，
        就出现在目录中，调用时排队等待提供方取走执行。
        """
        out = []
        with self._lock:
            for _provider, tools in self._providers.items():
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

    def _page_open_locked(self, provider, page_url, now):
        """判断某页面的工具是否打开（无锁版，调用方须已持锁）。

        超期未续报的登记视为僵尸（页面崩溃 / 标签被直接关闭而来不及注销），
        顺手清除，避免命令永远等一个不会来的页面。
        """
        target = normalize_url(page_url)
        if not target:
            return False
        pages = self._open_pages.get(provider, {})
        ts = pages.get(target)
        if ts is None:
            return False
        if (now - ts) > OPEN_WINDOW:
            pages.pop(target, None)
            return False
        return True

    # ---------- 轮询与命令队列 ----------
    def _set_page_open(self, provider, target, is_open, now):
        """登记 / 注销某页面的工具打开状态（调用方须已持锁）。

        关闭即注销：属于该页面的命令立刻失去归属，可被其他页面代收。
        """
        if not target:
            return
        pages = self._open_pages.setdefault(provider, {})
        if is_open:
            pages[target] = now
        else:
            pages.pop(target, None)

    def _take_mine(self, provider, c, target, now):
        """判断一条命令是否归本页面执行（调用方须已持锁）。

        取走规则：
          1. 目标就是本页面 —— 优先取走；
          2. 无目标页面 —— 公开命令，任何页面可取；
          3. 目标页面的工具没打开 —— 逸散，本页面代收。
        返回 True 表示取走。目标页面工具开着时不打印（每次轮询都会重扫，
        逐条打印会刷屏），真正的取件动作在取走分支里已记。
        """
        c_url = normalize_url(c.get("page_url") or "")
        cid = (c.get("request_id") or "")[:8]
        if not c_url:
            log("取走公开命令", c.get("tool"), "id=" + cid)
            return True
        if c_url == target:
            log("取走本页面命令", c.get("tool"), "id=" + cid)
            return True
        if not self._page_open_locked(provider, c_url, now):
            log("代收命令（目标页面工具未开）", c.get("tool"),
                "目标=" + c_url, "由=" + (target or "(未知)"), "id=" + cid)
            return True
        return False

    def _pick_commands_locked(self, provider, target, now):
        """按归属规则把队列拆为「本页面取走」与「留给别人」两部分（调用方须已持锁）。

        取走后把剩余队列写回，保证未被取走的命令留在原处等它的目标页面。
        """
        queue = self._queues.get(provider, [])
        mine, rest = [], []
        for c in queue:
            (mine if self._take_mine(provider, c, target, now) else rest).append(c)
        self._queues[provider] = rest
        return mine

    def poll(self, provider, page_url="", is_open=True):
        """记录心跳与工具开关状态，并按「同页面优先、目标没开就逸散」取走命令。

        每条命令都带目标页面地址。取命令时的规则：
          1. 目标页面与本页面一致 —— 直接取走（同页面优先）。
          2. 命令没有目标页面 —— 视为公开命令，任何页面可取（兼容旧调用）。
          3. 目标页面是别的页面，但它的工具当前没打开 —— 直接允许本页面代收，
             不再等待任何时间窗。
          4. 目标页面是别的页面，且它的工具开着 —— 留给它，不取。
        判断依据是各页面上报的「工具是否打开」，而非时间猜测，因此目标页面
        一关，属于它的命令立刻逸散到其他页面。
        @param provider 提供方标识
        @param page_url 本页面的地址（来自扩展心跳）
        @param is_open 本页面的工具（抽屉）当前是否打开
        @returns 本次取走的命令列表
        """
        target = normalize_url(page_url)
        now = time.time()
        with self._lock:
            self._last_poll[provider] = now
            self._set_page_open(provider, target, is_open, now)
            # 本页面工具已关闭：本次只注销登记，不取任何命令。
            # 否则「关闭时上报」这一次调用会顺手把属于本页面的命令取走并丢弃，
            # 命令被白白消耗，其他页面再也等不到它。
            if not is_open:
                return []
            return self._pick_commands_locked(provider, target, now)

    def push_command(self, provider, command):
        """把一条命令追加到该提供方的队列。

        命令里的 page_url（目标页面）由 dispatch 在构造命令时写入。
        """
        with self._lock:
            self._queues.setdefault(provider, []).append(command)

    # ---------- 工具调用转发与等待 ----------
    def _abort_request(self, provider, request_id):
        """超时善后：注销等待事件，并从队列撤回尚未被取走的命令（调用方须已持锁）。

        撤回是必要的：否则该命令会留在队列里，被提供方在下一次 poll 时
        当作新任务取走执行，而它对应的等待方早已超时离场，形成
        「执行了一个没人要的任务、真正的新任务却被排在后面」的错位。
        """
        self._events.pop(request_id, None)
        queue = self._queues.get(provider)
        if queue:
            self._queues[provider] = [c for c in queue
                                      if c.get("request_id") != request_id]

    def dispatch(self, provider, tool, params, silent=False, page_url=""):
        """把一次工具调用入队，并阻塞等待提供方回传结果。

        silent 仅随命令下发，供提供方决定是否在界面生成工具卡片；
        无论 silent 与否都等待真实结果，否则调用方只能拿到入队确认，
        无法得知动作是否真正生效。
        page_url 为发起调用的页面地址，用于把命令定向到该页面；为空时
        退化为公开命令，任何页面都可取。
        返回 (ok, data_or_error)。
        """
        request_id = str(uuid.uuid4())
        command = {
            "request_id": request_id,
            "tool": tool,
            "params": params or {},
            "silent": bool(silent),
            "page_url": page_url or "",          # 命令的目标页面：优先由它执行
        }
        event = threading.Event()
        with self._lock:
            self._events[request_id] = event
        self.push_command(provider, command)
        log("命令入队", tool, "目标页面=" + (normalize_url(page_url) or "(公开)"), "id=" + request_id[:8])
        if not event.wait(timeout=FORWARD_TIMEOUT):
            with self._lock:
                self._abort_request(provider, request_id)
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
