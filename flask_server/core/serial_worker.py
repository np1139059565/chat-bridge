"""AI 工具调用镜像插件 —— 串行工作队列（共享）

职责：提供「单后台线程 + 串行队列 + 幂等启动」的通用骨架，
供记忆保存、记忆蒸馏等需要「同一时刻只有一个写者」的模块复用。

为什么要共用：
  这类模块此前各自实现了一份几乎相同的「加锁队列 + 幂等 worker 线程」样板，
  代码重复，且并发正确性（运行标志复位与判空的原子性）需多处维护、容易改漏。
  集中到本模块后，并发骨架只此一份。

关键并发约定（务必遵守）：
  - 运行标志的复位与「队列是否为空」的判断必须在同一把锁内完成，
    否则会出现「判空通过 → 尚未复位 → 新任务入队 → 线程已退出」的丢唤醒，
    任务将永远不被处理。本模块在 _run 中严格保证了这一点。
  - 处理函数在锁外执行：绝不在持锁期间跑写库等重活，避免阻塞入队方。

依赖：collections、threading
"""
import collections
import threading


class SerialWorker:
    """单后台线程的串行工作队列。

    同一 key 只保留一个待处理项（去重）；重复提交时按 keep_first 决定
    是保留首次还是用最新覆盖。处理函数串行执行，单次异常不影响后续项。
    """

    def __init__(self, handler, on_error=None, keep_first=True, thread_name="serial-worker"):
        """初始化串行工作队列。

        @param handler     处理单个元素的函数，签名 handler(item)
        @param on_error    异常回调，签名 on_error(exc)；为 None 时静默吞掉
        @param keep_first  True=重复提交保留首次；False=用最新覆盖
        @param thread_name 后台线程名（便于调试时识别来源）
        """
        self._handler = handler                 # 单元素处理函数
        self._on_error = on_error               # 异常回调
        self._keep_first = keep_first           # 去重策略：保留首次 / 最新覆盖
        self._thread_name = thread_name         # 线程名
        self._order = collections.deque()       # 待处理 key 的 FIFO 顺序
        self._items = {}                        # key -> item（兼作去重集合与取值表）
        self._lock = threading.Lock()           # 保护 _order / _items / _running
        self._running = False                   # 后台线程是否在跑

    def submit(self, key, item):
        """投递一个待处理项；立即返回，不等待处理完成。

        @param key  去重键（同一 key 只保留一个待处理项）
        @param item 处理函数将收到的元素
        @returns 是否新增了待处理项（已在队列中则为 False）
        """
        with self._lock:                        # 入队与去重判断同锁
            if key in self._items:              # 该 key 已有待处理项
                if self._keep_first:            # 保留首次：忽略本次
                    return False
                self._items[key] = item         # 最新覆盖：替换元素，顺序不变
                return False
            self._order.append(key)             # 首次入队，记录顺序
            self._items[key] = item             # 记录元素
        self._ensure()                          # 确保后台线程在跑
        return True                             # 确为新增

    def _ensure(self):
        """确保后台线程在跑（幂等：重复调用只启动一个）。"""
        with self._lock:                        # 与 _run 的复位同锁，避免竞态
            if self._running:                   # 已在跑则直接返回
                return
            self._running = True                # 先置标志，再启动线程
        threading.Thread(target=self._run, daemon=True, name=self._thread_name).start()

    def _run(self):
        """后台线程主体：循环取元素串行处理，队列空则复位标志退出。"""
        while True:
            with self._lock:                    # 判空与复位同锁：杜绝丢唤醒
                if not self._order:             # 队列已空
                    self._running = False       # 复位标志，允许下次重新拉起
                    return                      # 退出线程，不空转占资源
                key = self._order.popleft()     # 取队首 key
                item = self._items.pop(key, None)  # 取出并移除元素
            if item is None:                    # 边界：元素已被覆盖取走等
                continue                        # 跳过，继续下一项
            try:
                self._handler(item)             # 锁外执行处理函数
            except Exception as e:              # 单元素失败不中断队列
                if self._on_error is not None:  # 有回调则上报
                    self._on_error(e)
