"""远程桥接 —— 微信事件分发

职责：
1. 接收 WeixinClient 回调的消息，抽出正文
2. 以「/」开头的消息交给指令处理
3. 其余消息包装成 external-call 卡片投给投递队列，由抽屉取走送进网页 AI

与 QQ 网关（qq_gateway.py）同构：网页 AI 看到的只是一条普通投递项，
感知不到消息来自 QQ 还是微信。

关键差异（配额约束）：
  微信 24 小时内最多 10 条独立消息，且不支持主动推送。
  因此本网关只负责「收」，推送由统一管线的微信适配器合并成一条发。
"""
import json
import time

import delivery_queue

from . import bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][weixin]", *args)


# 消息项类型（与 weixin_client 保持一致；此处在网关内直接判值，
# 避免仅为两个常量引入循环依赖）。
ITEM_TEXT = 1
ITEM_VOICE = 3


def extract_text(msg):
    """从一条微信消息里抽出正文。

    优先级：文本项 > 语音项的转写文字。
    必须分两轮扫描：单轮「先命中先返回」会让排在文本项之前的语音项抢先，
    导致图文/语音混合消息丢掉真正的文本正文。
    语音项的 text 是服务端已做好的识别结果，可直接使用，无需本地 ASR。

    @param msg 消息对象
    @returns 正文；无可用正文返回空串
    """
    items = [it for it in (msg.get("item_list") or []) if isinstance(it, dict)]
    # 第一轮：文本项优先（不论它在列表中的位置）
    for item in items:
        if item.get("type") == ITEM_TEXT:
            txt = (item.get("text_item") or {}).get("text") or ""
            if txt:
                return str(txt)
    # 第二轮：退回语音项的转写文字
    for item in items:
        if item.get("type") == ITEM_VOICE:
            txt = (item.get("voice_item") or {}).get("text") or ""
            if txt:
                return str(txt)
    return ""


def sender_of(msg):
    """取消息发送者标识。

    @param msg 消息对象
    @returns 用户标识；缺失返回空串
    """
    return msg.get("from_user_id") or ""


class WeixinGateway:
    """微信事件分发器：把微信消息变成卡片，把指令交给指令处理器。"""

    def __init__(self, on_command=None):
        """
        @param on_command 指令回调，签名 (client, user_id, msg_id, text) -> bool
        """
        self.client = None          # 由 RemoteBridge 在启动后注入
        self.on_command = on_command

    def handle_message(self, client, msg):
        """WeixinClient 的消息回调入口。

        @param client WeixinClient 实例
        @param msg    消息对象
        """
        self.client = client
        user_id = sender_of(msg)
        if not user_id:
            log("消息缺少发送者标识，忽略")
            return
        content = extract_text(msg)
        if not content:
            log("消息无可用正文（可能是图片/文件），忽略")
            return
        log("收到消息", "user=" + user_id[:8], "长度=" + str(len(content)))
        # 刷新「谁在跟我说话」：统一推送管线从 channel.target 读「最近用户」兜底，
        # 配额按用户消息重置（微信每条用户消息发放一个新回复池）。
        # 两条记账都在公共层，与 QQ 的窗口状态互不相干。
        from .channel import target as target_store, quota as quota_store
        target_store.weixin.note(user_id)
        quota_store.weixin.reset(user_id)
        self._dispatch_text(user_id, content, msg)

    def _dispatch_text(self, user_id, content, msg):
        """分派一条文本：以 / 开头走指令，其余投投递队列。

        @param user_id 发送者
        @param content 正文
        @param msg     原始消息对象
        """
        if content.startswith("/"):
            handled = bool(self.on_command
                           and self.on_command(self.client, user_id, msg.get("message_id") or "", content))
            if not handled:
                # 指令通道与聊天通道分离：无人认领的命令只回提示，不投给 AI
                self.reply_text(user_id, "未知指令：%s\n发送 /help 查看可用指令"
                                % str(content).strip().split(None, 1)[0])
            return
        self._deliver_as_card(user_id, content, msg)

    def _deliver_as_card(self, user_id, content, msg):
        """把微信消息包装成 external-call 卡片投给网页 AI。

        卡片来源标记为 weixin，供推送侧去重（不回推用户自己发的话）。
        @param user_id 发送者
        @param content 正文
        @param msg     原始消息对象
        """
        # 拼装委托公共层：三条通道共用同一份信封结构，
        # 避免各写一份后结构漂移、前端识别不到来源。
        from .channel import delivery
        delivery.deliver_text("weixin", user_id, content,
                              msg_id=msg.get("message_id") or "",
                              title="微信用户")

    def reply_text(self, user_id, text):
        """向微信回发一条提示文本。

        直接走客户端发送，不占用推送配额之外的额外逻辑：
        一次用户消息换一条回复，符合配额约束。
        @param user_id 接收方
        @param text    正文
        """
        if not self.client:
            log("微信客户端未就绪，无法回发提示")
            return
        ok, data = self.client.send_text(user_id, text)
        if not ok:
            log("回发提示失败：", data)
