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


def _resolve_target_page(site_key):
    """把站点标识解析为该站点当前在线的页面地址。

    多网页 AI 并存时，手机端发消息必须指明投给哪个页面，否则卡片会被
    任意页面的抽屉取走，造成「消息发到了别的 AI 那里」。

    解析顺序：
    1. 若已用 /page 接管某页面，且该页面属于该站点 → 用接管页；
    2. 否则在该站点的在线页面里取第一个（按地址排序，保证稳定）；
    3. 该站点无在线页面 → 返回空串，退回旧行为（任何页面可取）。
       宁可让它被广播取走，也不要因为解析不到而卡住消息。

    @param site_key 站点标识（glm / qianwen / yuanbao …）
    @returns {string} 页面地址；无法确定时为空串
    """
    key = str(site_key or "").strip()
    if not key:
        return ""
    try:
        import page_registry
        # 站点标识到域名片段的映射：站点 id 与域名主体基本一致，
        # 少数不一致（如 glm 对应 chatglm.cn）在下面单独列出。
        frag = _SITE_HOST_HINTS.get(key, key)
        online = page_registry.online()
        candidates = [u for u in online if frag in u]
        if not candidates:
            return ""
        # 接管页优先：用户显式指定过就尊重它
        active = page_registry.get_active()
        if active and active in candidates:
            return active
        return candidates[0]
    except Exception:
        # 解析失败不能影响发消息主流程
        return ""


# 站点 id → 域名片段。键为档案 id，值为该站点页面地址里出现的特征串。
# 只登记「id 与域名主体不一致」的站点；其余直接用 id 本身匹配。
_SITE_HOST_HINTS = {
    "glm": "chatglm",
    "wenxin": "wenxin",
    "deepseek": "deepseek",
    "qianwen": "qianwen",
    "yuanbao": "yuanbao",
    "xinghuo": "xinghuo",
    "kimi": "kimi",
}


class WebBridge:
    """网页版桥接总控：入站投卡、出站存箱、语音落盘。"""

    def _create_card(self, card_type, title, content, payload, log_hint="", extra="",
                     target_page=""):
        """向卡片总线投一张卡，返回卡片 id；失败返回空串。

        @param card_type   卡片类型
        @param title       标题
        @param content     卡片正文
        @param payload     结构化载荷
        @param log_hint    日志中的卡片名（如「图片卡片」）
        @param extra       日志附加信息（如张数）
        @param target_page 目标页面地址；非空时只有该页面的抽屉能取走。
                           多网页 AI 并存时用它把网页发出的消息投给指定站点的页面。
        @returns 卡片 id；失败空串
        """
        import card_bus
        try:
            card = card_bus.bus.create(
                source="web", card_type=card_type, title=title,
                content=content, payload=payload, target_page=target_page,
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

    def ingest_text(self, text, site_key=""):
        """把网页发来的一段文字投进卡片总线，送进网页 AI。

        复用与 QQ 完全相同的路径：造一张 external-call 卡片，
        由抽屉轮询取走、发送到网页 AI。

        @param text     用户输入的文本
        @param site_key 目标站点。多网页 AI 并存时，卡片按此投给对应页面，
                        避免被别的页面抢走；空串表示不限页面（旧行为）。
        @returns 卡片 id；失败返回空串
        """
        import json
        import time
        # 目标页面：优先取该站点已登记且在线的那一个
        target = _resolve_target_page(site_key)
        payload = {
            "type": "external-call",
            "nonce": "web-" + str(int(time.time() * 1000)),
            "request": str(text or ""),
            "source": "web",          # 来源标记：网页版
            "openid": "web-user",     # 单用户场景固定标识
            "msg_id": "",
            "from_voice": False,
            "page_url": target,
        }
        return self._create_card(
            card_type="external-call",
            title="网页用户",
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            payload={"source": "web", "openid": "web-user"},
            log_hint="文本卡片",
            target_page=target,
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
        # 拼装委托公共层：三条通道共用同一份实现，避免能力漂移。
        # image_names 是网页版特有字段（抽屉据此把图挂到对应消息上），
        # 通过 extra 透传，不影响其它通道。
        from remote_bridge.channel import delivery
        return delivery.deliver_images(
            "web", "web-user", sources=urls, text=text, title="网页图片",
            extra={"image_names": [str(n) for n in (image_names or []) if n]},
        )


    def ingest_file(self, path, name, size, text=""):
        """把网页上传的一个文件投成卡片，送进网页 AI。

        与图片的区别：文件是二进制，AI 看不见也不需要看见，
        它需要的是路径——拿到后自己按需调 read_file。
        因此卡片正文只写「文件在哪」，不塞内容。
        @param path 服务端落盘的绝对路径
        @param name 原始文件名
        @param size 体积（字节）
        @param text 随文件附带的说明文字；为空则自动生成一句
        @returns 卡片 id；失败返回空串
        """
        body = str(text or "").strip()
        # 没写说明时给 AI 一句上下文：谁发来的、什么文件、在哪
        if not body:
            body = "用户从网页发来文件：%s（%d 字节），已保存到 %s" % (name, size, path)
        payload = {
            "kind": "web-file",
            "path": str(path or ""),
            "name": str(name or ""),
            "size": int(size or 0),
            "text": body,
        }
        return self._create_card(
            card_type="web-file",
            title="网页文件",
            content=body,
            payload=payload,
            log_hint="文件卡片",
            extra="name=" + str(name or ""),
        )


# 全局单例
web = WebBridge()
