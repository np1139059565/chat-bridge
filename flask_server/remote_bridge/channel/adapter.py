"""远程桥接 —— 通道适配器协议

公共层负责「推什么、推给谁、推几条」这些与通道无关的决策；
适配器只负责「怎么把内容送出去」，即与平台协议相关的那部分。

这个分工决定了新增一条通道的成本：实现本协议 + 注册三条元数据，
不必再抄一遍去重、配额、组装、记账的流程。

元数据三件套（由各通道在构造时提供）：
    name    —— 通道标识，同时用作去重命名空间与活跃渠道标记
    dedupe  —— 已推集合实例
    quota   —— 配额策略实例
"""


class ChannelAdapter:
    """通道适配器基类。

    子类必须实现 send_text；其余方法按通道能力实现，不支持时抛
    NotImplementedError，由推送管线据此判断该通道能否处理该类内容。
    """

    # 通道标识：用于日志、去重命名空间、活跃渠道匹配
    name = ""

    def __init__(self, name, dedupe, quota):
        """构造适配器。

        @param name   通道标识
        @param dedupe 已推集合（channel.dedupe 的实例）
        @param quota  配额策略（channel.quota 的实例）
        """
        self.name = name
        self.dedupe = dedupe
        self.quota = quota
        # 按会话分锁：管线在锁内完成「读集合 → 推送 → 写回」，
        # 同一会话串行、不同会话互不阻塞。
        from .push_pipeline import ConvLocks
        self._conv_locks = ConvLocks()

    # ---------- 必须实现 ----------
    def send_text(self, target, text, markdown=False):
        """发送一条文本消息。

        @param target   收件人标识
        @param text     正文
        @param markdown 是否按 Markdown 发送
        @returns (是否成功, 平台返回数据)
        """
        raise NotImplementedError

    # ---------- 按能力实现 ----------
    def send_image(self, target, image_bytes):
        """发送一张图片。

        @param target      收件人标识
        @param image_bytes 图片二进制
        @returns (是否成功, 平台返回数据)
        """
        raise NotImplementedError("%s 通道不支持发图片" % self.name)

    def send_file(self, target, file_path, file_name):
        """发送一个文件。

        @param target    收件人标识
        @param file_path 本地文件绝对路径
        @param file_name 展示用文件名
        @returns (是否成功, 平台返回数据)
        """
        raise NotImplementedError("%s 通道不支持发文件" % self.name)

    # ---------- 可选覆盖 ----------
    def resolve_target(self, payload):
        """决定本次推送的收件人。

        默认实现：优先用上报体里带的标识，否则回退到「最近跟我说话的人」。
        各通道的标识字段名不同（QQ 是 openid），需要时覆盖。
        @param payload 上报体
        @returns 收件人标识；无从确定时返回空串
        """
        return payload.get("openid") or ""

    def push_media(self, recipient, items, push, ctx):
        """在文本推送之后，发送这批消息里的媒体（图片 / 文件 / 语音）。

        为什么媒体不能并入合并文本：合并后图片就变成一段文字路径，
        用户看不到图。故支持媒体的通道在这里单独发，返回成功条数。
        @param recipient 收件人
        @param items     本轮待推消息
        @param push      推送开关
        @param ctx       锁外预处理结果
        @returns 成功发送的媒体条数
        """
        return 0

    def merge_batch(self, items, push):
        """把一批消息合并成一条待发送正文。

        默认不合并：返回 None 表示「逐条发送」，由推送管线逐条组装。
        微信配额紧张，覆盖本方法返回合并后的长文本。
        @param items 本轮待推的消息列表
        @param push  推送开关字典
        @returns 合并后的文本；None 表示不合并
        """
        return None

    def supports(self, kind):
        """声明本通道支持的消息类别。

        @param kind 消息类别（user / tool / ai / image / file）
        @returns 支持返回 True
        """
        return True
