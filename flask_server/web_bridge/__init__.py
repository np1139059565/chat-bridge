"""网页版机器人 —— 包入口

对外提供 WebBridge 单例：把「手机网页」接入与 QQ 相同的底层链路。

定位（与 QQ 桥接的关系）：
- QQ 桥接：消息靠 QQ 被动回复窗口「推」给用户；
- 网页版：用户打开网页后「主动拉」新消息。
- 两者共用同一场对话（用户拍板 1A），底层收发都走既有「卡片总线 + 抽屉」。

三条链路：
1. 入站（网页 → 网页 AI）：网页发的文字/图片/语音，包装成卡片投进总线，
   由抽屉取走送进网页 AI，与 QQ 消息路径完全一致。
2. 出站（网页 AI → 网页）：AI 回复在推 QQ 的同时，也存一份进收件箱，
   网页按游标增量拉取。
3. 语音：AI 回复里的语音块合成 MP3 落到网页音频目录，网页拉到后自动播放。
"""
from . import web_inbox
import app_log


def log(*args):
    """统一前缀打印。"""
    app_log.info("[web]", *args)


class WebBridge:
    """网页版桥接总控：入站投卡、出站存箱、语音落盘。"""

    def _create_card(self, card_type, title, content, payload, log_hint="", extra=""):
        """向卡片总线投一张卡，返回卡片 id；失败返回空串。

        @param card_type 卡片类型
        @param title     标题
        @param content    卡片正文
        @param payload    结构化载荷
        @param log_hint   日志中的卡片名（如「图片卡片」）
        @param extra      日志附加信息（如张数）
        @returns 卡片 id；失败空串
        """
        import card_bus
        try:
            card = card_bus.bus.create(
                source="web", card_type=card_type, title=title,
                content=content, payload=payload,
            )
            seg = ["已投递" + log_hint, card.id[:8]]
            if extra:
                seg.append(extra)
            seg.append("等待抽屉取走")
            log(*seg)
            return card.id
        except Exception as e:
            log("投递" + log_hint + "失败：", e)
            return ""

    def ingest_text(self, text):
        """把网页发来的一段文字投进卡片总线，送进网页 AI。

        复用与 QQ 完全相同的路径：造一张 external-call 卡片，
        由抽屉轮询取走、发送到网页 AI。
        @param text 用户输入的文本
        @returns 卡片 id；失败返回空串
        """
        import json
        import time
        payload = {
            "type": "external-call",
            "nonce": "web-" + str(int(time.time() * 1000)),
            "request": str(text or ""),
            "source": "web",          # 来源标记：网页版
            "openid": "web-user",     # 单用户场景固定标识
            "msg_id": "",
            "from_voice": False,
            "page_url": "",
        }
        return self._create_card(
            card_type="external-call",
            title="网页用户",
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            payload={"source": "web", "openid": "web-user"},
            log_hint="文本卡片",
        )

    def ingest_images(self, data_urls, text="", image_names=None):
        """把网页发来的一组图片（可含文字）投成一张卡片，由抽屉一次贴进网页 AI。

        复用 QQ 图片的逆向流程：图片转 dataURL 放进 qq-image 卡片，
        抽屉取到后调 auto_send_image 贴进网页 AI 输入框。
        多图与文字放同一张卡片：抽屉会把它们一次性贴入输入框再回车，
        保证「图文合一」，不拆成多条消息。
        @param data_urls 图片 dataURL 数组
        @param text      随图附带的文字；为空时补「用户截图」给 AI 上下文
        @returns 卡片 id；失败返回空串
        """
        urls = [str(u) for u in (data_urls or []) if u]
        if not urls:
            return ""
        payload = {
            "kind": "qq-image",
            # data_urls：图片数组（前端据此一次贴多张）
            "data_urls": urls,
            # data_url：单张兼容字段（旧消费端只认它时取第一张）
            "data_url": urls[0],
            "openid": "web-user",
            "path": "",
            "text": (text or "").strip() or "用户截图",
            # image_names：图片在服务端的文件名（与收件箱同源）。
            # 抽屉据此把图片挂到对应消息上，渲染时按名取图显示，
            # 不依赖网页 DOM（网页里用户图未必是 img 元素）。
            "image_names": [str(n) for n in (image_names or []) if n],
        }
        return self._create_card(
            card_type="qq-image",     # 沿用既有图片卡片类型，抽屉按此消费
            title="网页图片",
            content="（网页图片，自动贴入网页 AI 输入框）",
            payload=payload,
            log_hint="图片卡片",
            extra="张数=" + str(len(urls)),
        )


# 全局单例
web = WebBridge()
