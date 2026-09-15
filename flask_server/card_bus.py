"""卡片总线：统一登记外部卡片、投递给镜像插件、等待结果回填、超时唤醒。

对外只暴露一个同步语义：调用方登记一张卡片后一直等待，
直到结果按卡片 id 回填，或等待达到上限后超时。
"""
import threading
import time
import uuid

# 卡片状态常量
# 说明：外部卡片采用「发送即结束」，只有 pending（待投递）与 done（已投递）两个常态；
# error / timeout 保留以兼容异常路径。counting / sending / waiting_reply 属历史遗留，已移除。
STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_TIMEOUT = "timeout"

# 默认等待上限（毫秒）
DEFAULT_TIMEOUT_MS = 120000


class Card:
    """单张卡片的数据载体。"""

    def __init__(self, source, card_type, title, content, payload, timeout_ms):
        self.id = str(uuid.uuid4())
        self.source = source or "external"
        self.type = card_type or ""   # 信封类型，如 debug-chrome-req
        self.title = title or ""
        self.content = content or ""
        self.payload = payload or {}
        self.status = STATUS_PENDING
        self.created_at = int(time.time() * 1000)
        self.timeout_ms = int(timeout_ms or DEFAULT_TIMEOUT_MS)
        self.result = None
        self.error = None
        self.delivered = False   # 是否已投递给镜像插件

    def to_dict(self):
        return {
            "id": self.id,
            "source": self.source,
            "type": self.type,
            "title": self.title,
            "content": self.content,
            "payload": self.payload,
            "status": self.status,
            "created_at": self.created_at,
            "timeout_ms": self.timeout_ms,
            "result": self.result,
            "error": self.error,
        }


class CardBus:
    """卡片总线：线程安全地登记、投递、回填、超时。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._cards = {}
        self._events = {}
        self._results = {}

    def create(self, source, card_type, title, content, payload, timeout_ms):
        """登记一张卡片，返回卡片对象。"""
        card = Card(source, card_type, title, content, payload, timeout_ms)
        with self._lock:
            self._cards[card.id] = card
            self._events[card.id] = threading.Event()
        return card

    def set_status(self, card_id, status):
        with self._lock:
            card = self._cards.get(card_id)
            if card:
                card.status = status

    def claim_pending(self):
        """取走尚未投递的卡片（镜像插件轮询用），标记为已投递。"""
        out = []
        with self._lock:
            for card in self._cards.values():
                if not card.delivered:
                    card.delivered = True
                    # 投递后状态仍为 pending：真正「完成」由镜像插件回填确认时置为 done
                    out.append(card.to_dict())
        out.sort(key=lambda c: c["created_at"])
        return out

    def resolve(self, card_id, result, status=STATUS_DONE):
        """按 id 回填结果，唤醒等待方。"""
        with self._lock:
            card = self._cards.get(card_id)
            event = self._events.get(card_id)
            if card:
                card.status = status
                card.result = result
            if event:
                self._results[card_id] = result
                event.set()
        return bool(card)

    def wait(self, card_id, timeout_ms=None):
        """阻塞等待结果。返回 (ok, result_or_error)。"""
        with self._lock:
            card = self._cards.get(card_id)
            event = self._events.get(card_id)
        if not card or not event:
            return False, "UNKNOWN_CARD"
        limit = (timeout_ms if timeout_ms is not None else card.timeout_ms) / 1000.0
        if not event.wait(timeout=limit):
            with self._lock:
                card.status = STATUS_TIMEOUT
                card.error = "TIMEOUT"
            return False, "TIMEOUT"
        with self._lock:
            result = self._results.pop(card_id, None)
        return True, result

    def get(self, card_id):
        with self._lock:
            card = self._cards.get(card_id)
            return card.to_dict() if card else None


# 全局单例
bus = CardBus()
