"""通用投递队列：一端登记、另一端取走的中转服务。

队列只负责把一段载荷从一端送到另一端，不解释载荷语义，任意两端可对接。
接口语义保持「发送即结束」：登记即返回，不等待取件方回填结果，因此不存在超时失败；
取件方轮询取走尚未确认的条目，回执「已展示」后该条目不再投递，按 id 去重。

典型链路：
1. 投递端登记载荷，队列返回条目 id，请求立即结束；
2. 接收端轮询取走尚未确认的条目；
3. 接收端展示后调用确认回执，此后该条目不再投递；确认之前可被反复取走；
4. 进展由接收端通过独立通道主动推送，队列不参与。

线程安全：所有对条目表的读写都在锁保护下进行。
"""
import threading
import time
import uuid

# 条目状态常量：登记后即处于待投递态。
STATUS_PENDING = "pending"

# 条目总数上限取自全项目统一来源（app_limits）：条目表只增不减会内存泄漏
# （载荷可能含完整 base64，单条可达 1MB+）。超过此上限时，
# 优先丢弃「已被确认展示」的最旧条目，未确认的始终保留。
from app_limits import MAX_CARDS


class DeliveryItem:
    """单条投递项的数据载体。

    字段说明：
    - id         ：全局唯一标识（uuid4），用于轮询去重
    - source     ：来源标识（默认 external），供前端区分展示
    - type       ：信封类型，决定接收方如何解读 content
    - content    ：投递正文
    - payload    ：附加结构化数据，随条目一并投递
    - status     ：pending（待投递）
    - delivered  ：是否已被某个接收方确认「已展示」
    """

    def __init__(self, source, card_type, title, content, payload, target_page=""):
        self.id = str(uuid.uuid4())
        self.source = source or "external"
        self.type = card_type or ""
        self.title = title or ""
        self.content = content or ""
        self.payload = payload or {}
        self.status = STATUS_PENDING
        self.created_at = int(time.time() * 1000)
        # target_page：目标页面地址。空串表示不限（任何取件方可取），
        # 非空时只有该地址对应的取件方能取走，用于多路隔离。
        self.target_page = str(target_page or "")
        # delivered：是否已被某个接收方确认「已展示」。
        # 为 false 时任何接收方都可取走（可反复取走）；
        # 直到有接收方回执，才置 true 并停止投递。
        self.delivered = False

    def to_dict(self):
        """转为可 JSON 序列化的字典（供 API 返回）。"""
        return {
            "id": self.id,
            "source": self.source,
            "type": self.type,
            "title": self.title,
            "content": self.content,
            "payload": self.payload,
            "status": self.status,
            # delivered：是否已被确认展示。外部据此区分「待投递」与「已送达」。
            "delivered": bool(self.delivered),
            "created_at": self.created_at,
            # target_page：目标页面地址（空串=不限）。
            "target_page": self.target_page,
        }


# 慢锁阈值（毫秒）：等锁或持锁超过此值即告警。
# 队列被多个通道共用，若某次持锁过久，各通道都会排队等待。
# 超阈值才记录，正常毫秒级操作不产生日志。
_SLOW_LOCK_MS = 100.0


class TimedLock:
    """带耗时监控的锁：记录等锁与持锁耗时，超阈值即告警。

    语义与 `with lock:` 一致，只是多了计时。正常毫秒级操作不产生日志。
    """

    def __init__(self, lock, op):
        """@param lock 被包裹的锁；@param op 操作名（日志区分用）"""
        self._lock = lock
        self._op = op

    def __enter__(self):
        """获取锁并记录等待时长。"""
        import time
        self._t0 = time.perf_counter()
        self._lock.acquire()
        self._wait_ms = (time.perf_counter() - self._t0) * 1000.0
        self._t1 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        """释放锁并记录持有时长；超阈值则告警。"""
        import time
        import app_log
        hold_ms = (time.perf_counter() - self._t1) * 1000.0
        self._lock.release()
        if self._wait_ms >= _SLOW_LOCK_MS or hold_ms >= _SLOW_LOCK_MS:
            app_log.warn("[delivery_queue]",
                         "%s 等锁=%.0fms 持锁=%.0fms" % (self._op, self._wait_ms, hold_ms))
        return False


class DeliveryQueue:
    """通用投递队列：线程安全地登记与取件。

    内部结构：
    - _items ：id → DeliveryItem，条目数据
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._items = {}

    def _timed(self, op):
        """返回一个带耗时监控的锁上下文管理器，超阈值即告警。

        @param op 操作名，用于日志区分
        """
        return TimedLock(self._lock, op)

    def create(self, source, card_type, title, content, payload, target_page=""):
        """登记一条投递项，返回条目对象。

        登记后按上限裁剪：优先丢弃「已被确认展示」的最旧条目，
        未确认的始终保留，避免条目表无界增长导致内存泄漏。

        @param target_page 目标页面地址；非空时只有该地址的取件方能取走。
        """
        item = DeliveryItem(source, card_type, title, content, payload, target_page)
        with self._timed("create"):
            self._items[item.id] = item
            self._trim_locked()
        return item

    def _trim_locked(self):
        """按上限裁剪已确认的旧条目（调用方须已持锁）。

        只删 delivered=True 的条目，从最旧的开始；未确认的一条不删。
        """
        if len(self._items) <= MAX_CARDS:
            return
        delivered = [c for c in self._items.values() if c.delivered]
        delivered.sort(key=lambda c: c.created_at)
        need = len(self._items) - MAX_CARDS
        for c in delivered[:need]:
            self._items.pop(c.id, None)

    def claim_pending(self, page_url=""):
        """取走尚未被确认的条目（接收方轮询用）。

        只要条目没被任何接收方确认「已展示」，且归属校验通过，就可以取走；
        不设租约、不设占位：确认之前可被反复取走，直到有接收方回执为止。
        重复投递由接收方按条目 id 去重。

        归属规则：
        - 条目 target_page 为空：不限页面，任何取件方可取；
        - 条目 target_page 非空：只有该页面能取。

        @param page_url 取件方声明的页面地址；空串表示未声明，
                        此时只返回不限页面的条目（宁可少给，不可串台）
        @returns {list} 条目字典列表（按创建时间升序）
        """
        me = str(page_url or "").strip()
        out = []
        with self._timed('claim_pending'):
            for item in self._items.values():
                if item.delivered:
                    continue
                if item.target_page and item.target_page != me:
                    continue
                out.append(item.to_dict())
        out.sort(key=lambda c: c["created_at"])
        return out

    def confirm_delivered(self, card_id):
        """确认条目已由某接收方展示，此后不再投递。

        这是条目停止投递的唯一条件；重复确认是幂等的。
        """
        with self._timed('confirm_delivered'):
            item = self._items.get(card_id)
            if not item:
                return False
            item.delivered = True
        return True

    def get(self, card_id):
        """查询单条投递项的状态快照；不存在返回 None。"""
        with self._timed('get'):
            item = self._items.get(card_id)
            return item.to_dict() if item else None


# ---------- 两个实例，同一个类，物理隔离 ----------
# bus：通用通道，承载常规投递项。
# command_bus：指令通道，承载下发给执行端的指令项。
#
# 为什么用两个实例而不是两个类：两者行为完全一致（登记、裁剪、确认），
# 差异只在「谁能看见」，那是实例归属问题、不是行为问题。
#
# 为什么必须隔离：两类投递项的接收方不同，共用一条队列时存在串台风险。
bus = DeliveryQueue()
command_bus = DeliveryQueue()
