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

# 「目标页独占」窗口（秒）：命令带目标页（page_url）时，该页在这段时间内独占命令，
# 其他页面不得代收；超时仍未被取走（如目标页没打开 debug-chrome），才进入逸散阶段。
# 取值贴合扩展的常规轮询间隔（5 秒），保证目标页至少有一次轮询机会。
TARGET_HOLD = 5.0


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

    def _escape_take(self, provider, h_url, target, now, tag):
        """逸散阶段的取件判断（调用方须已持锁）。

        逸散优先级：
          1. 本页面（host_page_url）就是当前轮询页 —— 取走；
          2. 本页面当前开着 debug-chrome —— 留给本页面，其他页面不取；
          3. 本页面没开 —— 其他页面可随机取走（谁先轮询谁得）。
        @param h_url 本页面地址（规整后）
        @param target 当前轮询页地址（规整后）
        @param tag 日志标签（已含原因 / 工具名 / 请求 id，避免参数过多）
        @returns 是否取走
        """
        # 1. 当前轮询页就是本页面 → 优先取走
        if h_url and h_url == target:
            log("逸散取走（本页面）", tag)
            return True
        # 2. 本页面开着 debug-chrome → 留给它
        if h_url and self._page_open_locked(provider, h_url, now):
            return False
        # 3. 本页面没开 → 其他页面随机取走
        log("逸散取走（其他页面）", tag,
            "本页面=" + (h_url or "(无)"), "由=" + (target or "(未知)"))
        return True

    def _take_mine(self, provider, c, target, now):
        """判断一条命令是否归本页面执行（调用方须已持锁）。

        取走规则（按用户约定）：
          1. 无目标页（如 push_message）—— 跳过独占，直接进入逸散；
          2. 目标就是本页面 —— 取走（目标页随时优先）；
          3. 有目标页且在独占窗口（TARGET_HOLD）内 —— 只有目标页可取，其他页面不取；
          4. 独占窗口已过 —— 进入逸散：优先本页面，本页面没开才随机给其他页面。
        返回 True 表示取走。
        """
        c_url = normalize_url(c.get("page_url") or "")        # 目标页
        h_url = normalize_url(c.get("host_page_url") or "")   # 本页面
        cid = (c.get("request_id") or "")[:8]
        tool = c.get("tool")
        created = c.get("created_at") or 0

        # 规则 1：无目标页 → 直接逸散
        if not c_url:
            return self._escape_take(provider, h_url, target, now, "公开命令 %s id=%s" % (tool, cid))
        # 规则 2：目标就是本页 → 取走
        if c_url == target:
            log("取走本页面命令", tool, "id=" + cid)
            return True
        # 规则 3：目标页独占窗口内 → 留给目标页
        if (now - created) < TARGET_HOLD:
            return False
        # 规则 4：窗口已过 → 逸散
        return self._escape_take(provider, h_url, target, now, "窗口超时逸散 %s id=%s" % (tool, cid))

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
        """记录心跳与工具开关状态，并按「目标页独占 → 逸散」取走命令。

        每条命令可带两个地址：目标页（page_url）与本页面（host_page_url）。
        取命令规则见 _take_mine：
          1. 无目标页（如 push_message）—— 直接进入逸散。
          2. 目标页 = 本页 —— 取走。
          3. 有目标页且在独占窗口（TARGET_HOLD）内 —— 只有目标页可取，其他页面不取。
          4. 独占窗口已过 —— 逸散：优先本页面，本页面没开才随机给其他页面。
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

    def dispatch(self, provider, tool, params, silent=False, page_url="", host_page_url=""):
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
            "page_url": page_url or "",              # 目标页面：独占窗口内优先由它执行
            "host_page_url": host_page_url or "",    # 本页面：逸散阶段优先回投给它
            "created_at": time.time(),               # 入队时刻：用于计算目标页独占窗口
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
