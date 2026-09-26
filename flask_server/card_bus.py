"""卡片总线：统一登记外部卡片、投递给镜像插件。

外部卡片采用「发送即结束」：登记即返回，不等待镜像插件回填结果，
因此不存在超时失败。任务进展由网页 AI 通过 push_message 主动推送给发起方。

典型调用链（外部系统 → 网页 AI）：
1. 外部系统 POST /api/cards，本模块 create() 登记卡片，请求立即返回；
2. 镜像插件 GET /api/cards/pending 轮询，本模块 claim_pending() 交出尚未确认的卡片；
3. 镜像插件把卡片渲染进列表后，调用 confirm_delivered() 回执「已展示」，
   此后该卡片不再投递；在此之前任何客户端都可反复取走，直到有人确认为止；
4. 镜像插件把卡片内容发送给网页 AI，任务进展由网页 AI 主动推送。

线程安全：所有对 _cards 的读写都在 _lock 保护下进行。
"""
import threading
import time
import uuid

# 卡片状态常量：外部卡片采用「发送即结束」，登记后即处于待投递态。
STATUS_PENDING = "pending"


class Card:
    """单张卡片的数据载体。

    字段说明：
    - id         ：全局唯一标识（uuid4），用于轮询去重
    - source     ：来源标识（默认 external），供前端区分展示
    - type       ：信封类型（如 external-call），决定接收方如何解读 content
    - content    ：投递给网页 AI 的正文
    - payload    ：附加结构化数据，随卡片一并投递
    - status     ：pending（待投递）
    - delivered  ：是否已被某个客户端确认「已展示」
    """

    def __init__(self, source, card_type, title, content, payload):
        self.id = str(uuid.uuid4())
        self.source = source or "external"
        self.type = card_type or ""   # 信封类型，如 external-call
        self.title = title or ""
        self.content = content or ""
        self.payload = payload or {}
        self.status = STATUS_PENDING
        self.created_at = int(time.time() * 1000)
        # delivered：是否已被某个客户端确认「已展示」。
        # 为 false 时任何客户端都可取走（可反复取走）；
        # 直到有客户端回执，才置 true 并停止投递。
        self.delivered = False

    def to_dict(self):
        """转为可 JSON 序列化的字典（供 API 返回给前端）。"""
        return {
            "id": self.id,
            "source": self.source,
            "type": self.type,
            "title": self.title,
            "content": self.content,
            "payload": self.payload,
            "status": self.status,
            "created_at": self.created_at,
        }


class CardBus:
    """卡片总线：线程安全地登记与投递。

    内部结构：
    - _cards ：id → Card，卡片数据
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cards = {}

    def create(self, source, card_type, title, content, payload):
        """登记一张卡片，返回卡片对象。"""
        card = Card(source, card_type, title, content, payload)
        with self._lock:
            self._cards[card.id] = card
        return card

    def claim_pending(self):
        """取走尚未被确认的卡片（镜像插件轮询用）。

        只要卡片没被任何客户端确认「已展示」，任何客户端都可以取走；
        不设租约、不设占位：确认之前可被反复取走，直到有客户端回执为止。
        重复投递由接收方按卡片 id 去重。
        """
        out = []
        with self._lock:
            for card in self._cards.values():
                if card.delivered:
                    continue
                out.append(card.to_dict())
        out.sort(key=lambda c: c["created_at"])
        return out

    def confirm_delivered(self, card_id):
        """确认卡片已由某客户端生成并展示，此后不再投递。

        客户端把卡片渲染进列表后调用。这是卡片停止投递的唯一条件：
        在收到确认之前，任何客户端都可以反复取走该卡片。
        重复确认是幂等的。
        """
        with self._lock:
            card = self._cards.get(card_id)
            if not card:
                return False
            card.delivered = True
        return True

    def get(self, card_id):
        """查询单张卡片的状态快照；不存在返回 None。"""
        with self._lock:
            card = self._cards.get(card_id)
            return card.to_dict() if card else None


# 全局单例：路由与业务模块统一通过 bus 访问，保证卡片状态全局一致
bus = CardBus()
