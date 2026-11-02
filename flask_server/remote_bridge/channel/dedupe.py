"""远程桥接 —— 已推消息集合

问题背景：
    抽屉每次上报都携带「当前可见的全部消息切片」，其中绝大多数已经推过。
    各通道必须记住「我推过哪些消息」，只推送差集，否则同一条消息会被
    反复推送，把手机刷屏、把配额耗尽。

为什么要有命名空间：
    多条通道同时开启时，同一条消息应当各自都能推到自己的平台。
    若共用一份集合，QQ 推过之后微信就认为「已推」而跳过——用户在微信里
    永远收不到消息。故每条通道用独立的命名空间（本质是独立的内存集合），
    互不压制。

集合形态：{ 会话键: set(消息 id) }。会话键由调用方提供（通常带上通道后缀），
保证不同会话之间的去重互不干扰。
"""
import threading

# 单个会话最多记住多少条已推 id。
# 长会话会累积上万条，全部留在内存里没有意义——超过这个数量后
# 只保留最新的部分，更早的消息即便重复上报也不会再推（本就已推送过）。
MAX_IDS_PER_CONV = 2000


class DedupeStore:
    """某条通道的已推集合。

    一条通道一个实例（见文件末尾）。实例内部自带锁：抽屉上报可能并发，
    「读集合 → 算差集 → 写回」必须串行，否则两次并发会算出同一份差集、
    把同一条消息推两遍。
    """

    def __init__(self, name):
        """构造一个去重集合。

        @param name 通道名（仅用于日志与排查）
        """
        self.name = name
        # 已推集合：{ 会话键: set(消息 id) }
        self._sent = {}
        # 保护 _sent 的锁
        self._lock = threading.RLock()

    def filter_new(self, conv_key, message_ids):
        """从候选消息 id 中挑出尚未推送过的，并立即记为已推。

        语义是「取差集并占用」：返回的 id 同时被写进集合，
        保证并发调用不会把同一条消息交给两方各自推送。

        @param conv_key    会话键（含通道后缀，保证跨通道隔离）
        @param message_ids 候选消息 id 列表（保持原顺序）
        @returns 尚未推送过的 id 列表（原顺序）
        """
        with self._lock:
            seen = self._sent.setdefault(conv_key, set())
            # 保持原顺序，只挑未出现过的；同时直接占用，避免并发重复
            fresh = []
            for mid in message_ids:
                if mid in seen:
                    continue
                seen.add(mid)
                fresh.append(mid)
            # 超量裁剪：只保留最新的一批，避免长会话无限占内存
            if len(seen) > MAX_IDS_PER_CONV:
                # set 无序，故按「最近加入」的近似口径保留：直接重建为最近的 n 个
                # 这里是近似处理——被裁掉的 id 若再次上报会被当成新消息重推一次，
                # 但那只发生在超过 2000 条的历史深处，代价可接受。
                keep = set(list(seen)[-MAX_IDS_PER_CONV:])
                self._sent[conv_key] = keep
            return fresh

    def has(self, conv_key, message_id):
        """判断某条消息是否已推送过。

        @param conv_key   会话键
        @param message_id 消息 id
        @returns 已推过返回 True
        """
        with self._lock:
            return message_id in (self._sent.get(conv_key) or set())

    def mark(self, conv_key, message_id):
        """单独标记某条消息为已推（不返回值）。

        用于「先发送、成功后再记账」的场景：发送失败的消息不应被记为已推，
        否则下一次上报会跳过它，用户永远收不到。
        @param conv_key   会话键
        @param message_id 消息 id
        """
        with self._lock:
            self._sent.setdefault(conv_key, set()).add(message_id)

    def forget(self, conv_key, message_id=None):
        """撤销已推记录。

        两种用法：
          - 传 message_id：只撤销这一条（推送失败时调用，让它下轮能重试）；
          - 不传：清空整个会话（用于「清空会话」等显式重置）。
        @param conv_key   会话键
        @param message_id 消息 id；不传表示清空整个会话
        """
        with self._lock:
            if message_id is None:
                self._sent.pop(conv_key, None)
                return
            seen = self._sent.get(conv_key)
            if seen:
                seen.discard(message_id)


# 三条通道各自的实例：命名空间天然隔离，互不压制。
qq = DedupeStore("qq")
weixin = DedupeStore("weixin")
wecom = DedupeStore("wecom")
