"""远程桥接 —— QQ 事件分发

职责：
1. 接收 QQClient 回调的事件，只处理单聊消息 C2C_MESSAGE_CREATE
2. 以「/」开头的消息交给指令处理
3. 其余消息：刷新被动回复窗口，并包装成 external-call 卡片投给卡片总线，
   由抽屉轮询取走、发送进网页 AI

包装成卡片后，网页 AI 看到的只是一条普通外部卡片，感知不到 QQ 的存在。
"""
import time

import card_bus

from . import message_router


def log(*args):
    """统一前缀打印。"""
    print("[bridge][gateway]", *args)


# C2C 单聊消息事件类型
EVENT_C2C_MESSAGE = "C2C_MESSAGE_CREATE"


def _extract(d):
    """从事件数据里取出关键字段。

    @return (openid, content, msg_id)；缺字段时对应值为空串
    """
    # 单聊事件的用户标识位于 author.user_openid（群聊场景则为 member_openid）
    author = d.get("author") or {}
    openid = author.get("user_openid") or ""
    content = d.get("content") or ""
    # 消息 id：被动回复要引用它，事件体顶层字段名为 id
    msg_id = d.get("id") or ""
    return openid, str(content).strip(), msg_id


class QqGateway:
    """QQ 事件分发器：把 QQ 消息变成卡片，把指令交给指令处理器。"""

    def __init__(self, on_command=None):
        """
        @param on_command 指令回调，签名 (qq_client, openid, msg_id, text) -> bool
        """
        self.qq_client = None        # 由 RemoteBridge 在启动后注入
        self.on_command = on_command

    def handle_event(self, event_type, data):
        """QQClient 的事件回调入口。"""
        if event_type != EVENT_C2C_MESSAGE:
            return
        openid, content, msg_id = _extract(data)
        if not openid or not content:
            log("事件缺少 openid 或 content，忽略")
            return
        log("收到单聊消息", "openid=" + openid[:8], "长度=" + str(len(content)))

        # 用户发消息即续期：刷新被动回复窗口
        if msg_id:
            message_router.note_incoming(openid, msg_id)

        # 指令：以「/」开头，交给指令处理器
        if content.startswith("/"):
            if self.on_command and self.on_command(self.qq_client, openid, msg_id, content):
                return

        # 普通消息：包装成外部卡片，投给卡片总线
        self._deliver_as_card(openid, content, msg_id)

    def _deliver_as_card(self, openid, content, msg_id):
        """把 QQ 消息包装成 external-call 卡片，登记到卡片总线。

        卡片内容里带上来源标记，供推送侧去重（不回推用户自己发的话）。
        """
        payload = {
            "type": "external-call",
            "nonce": "qq-" + str(int(time.time() * 1000)),
            "request": content,
            "source": "qq",
            "openid": openid,
            "msg_id": msg_id,
            "page_url": "",          # 不指定目标页面，谁打开着抽屉谁取走
        }
        try:
            import json
            card = card_bus.bus.create(
                source="qq",
                card_type="external-call",
                title="QQ 用户",
                content=json.dumps(payload, ensure_ascii=False, indent=2),
                payload={"source": "qq", "openid": openid, "msg_id": msg_id},
            )
            log("已投递卡片", card.id[:8], "等待抽屉取走")
        except Exception as e:
            log("投递卡片失败：", e)
