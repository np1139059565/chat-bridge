"""远程桥接 —— 消息推送准入判断

职责：判断一条上报的消息是否允许推送到手机（QQ / 微信等）。
从 message_router.py 抽出：后者已贴近仓库行数上限，而「什么该推、什么不该推」
本身也是一个独立且容易出错的关注点，单独成模块更便于审阅与测试。

核心规则（每条都对应一次真实事故）：
- 工具结果一律不推：它是排查用的 JSON，体积大、对用户无价值；
  刷新页面后会随历史消息重新上报，曾导致用户只发了指令却收到一堆 JSON。
- 用户自己发的消息不推：避免把用户刚说的话复读回去。
- 按设置页开关过滤 user / ai 两类。

依赖：message_parse（分类与来源判定）
"""
from .message_parse import _classify, _has_qq_source


def should_push(m, push):
    """判断一条消息是否应当推送到手机。

    @param m    消息对象
    @param push 推送开关字典（push.user / push.ai）
    @returns 应当推送为 True
    """
    kind = _classify(m)
    # 工具结果绝不推送到手机：它是排查用的 JSON，体积大、对用户无价值，
    # 且刷新页面后极易被重推，造成用户「只发了指令却收到一堆 JSON」的困惑。
    # 需要看工具结果时，在网页抽屉里看即可，不该刷屏到手机。
    if kind == "tool":
        return False
    # 推送开关：剩下两类（user / ai）各自控制
    if not push.get(kind, True):
        return False
    # 去重：用户自己发来的消息不回推，避免把刚说的话复读回去
    return not _has_qq_source(m)
