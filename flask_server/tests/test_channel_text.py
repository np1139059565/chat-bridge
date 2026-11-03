"""公共层 —— 正文组装的契约测试

测的是 channel/text.py，不针对任何具体通道。

为什么放在公共层：截断、正文提取、来源判定这些逻辑原先在企微与微信
两个适配器里各写一份，且两份逐字相同。抽到公共层后，测试也应守在这一层——
否则改坏公共层，各通道的测试可能照样全绿。

本文件守住五条契约：
  1. 纯工具调用不出正文（内部工作过程是噪音）；
  2. 带正文的工具调用要出正文，且工具参数不进正文；
  3. 普通代码块保留（用户可能确实要看代码）；
  4. 超长文本截断保留首尾，短文本不动；
  5. 自己通道发出去的卡片要能被识别出来，避免复读。

运行：python -m pytest tests/test_channel_text.py -q
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

from remote_bridge.channel import text as text_store  # noqa: E402


def _call_block(tool="x", params=None):
    """构造一个工具调用代码块。"""
    return {"type": "code",
            "code": json.dumps({"type": "bridge-chat-call",
                                "tool": tool,
                                "parameters": params or {}})}


def test_pure_tool_call_yields_empty_body():
    """只有工具调用、没有正文时，不产出可推文本。"""
    m = {"id": "t1", "role": "assistant",
         "blocks": [_call_block()]}
    assert text_store.extract_text(m, {}) == ""
    assert text_store.body_of(m, {}, "wecom") == ""


def test_text_with_tool_call_still_yields_body():
    """带正文的工具调用必须保住正文，不能因附带工具调用而整条丢掉。"""
    m = {"id": "t2", "role": "assistant",
         "blocks": [{"type": "paragraph", "text": "我查一下"},
                    _call_block()]}
    body = text_store.body_of(m, {}, "wecom")
    assert "我查一下" in body


def test_tool_params_excluded_from_body():
    """工具调用的参数（JSON）不能进正文——手机上是一屏花括号。"""
    m = {"id": "t3", "role": "assistant",
         "blocks": [{"type": "paragraph", "text": "执行中"},
                    _call_block("run_command", {"command": "import subprocess"})]}
    body = text_store.body_of(m, {}, "wecom")
    assert "执行中" in body
    assert "subprocess" not in body


def test_real_code_block_kept():
    """普通代码块保留：用户可能确实要看代码。"""
    m = {"id": "t4", "role": "assistant",
         "blocks": [{"type": "paragraph", "text": "写法："},
                    {"type": "code", "code": "print(1)"}]}
    body = text_store.body_of(m, {}, "wecom")
    assert "print(1)" in body


def test_truncate_keeps_head_and_tail():
    """超长文本截断时保留首尾——开头是结论，结尾是收尾。"""
    long_text = "开头" + ("填充" * 2000) + "结尾"
    cut = text_store.truncate(long_text)
    assert cut.startswith("开头")
    assert cut.endswith("结尾")
    assert "省略" in cut


def test_truncate_short_unchanged():
    """未超上限的文本原样返回。"""
    assert text_store.truncate("短") == "短"


def test_truncate_honors_custom_limit():
    """可传自定义上限：微信上限比企微短，属通道固有差异。"""
    long_text = "甲" * 500
    cut = text_store.truncate(long_text, 100)
    assert len(cut) <= 100 + 30  # 允许省略号的少量超出


def test_own_source_detected():
    """自己通道投出去的卡片能被识别出来，避免复读。"""
    env = {"type": "external-call", "source": "wecom", "request": "hi"}
    m = {"id": "w1", "role": "user",
         "blocks": [{"type": "code", "code": json.dumps(env)}]}
    assert text_store.is_own_source(m, "wecom") is True
    # 换个通道名就不该命中
    assert text_store.is_own_source(m, "qq") is False


def test_check_own_can_be_disabled():
    """check_own=False 时跳过来源判断（微信由管线在上游过滤）。"""
    env = {"type": "external-call", "source": "weixin", "request": "hi"}
    m = {"id": "w2", "role": "user",
         "blocks": [{"type": "code", "code": json.dumps(env)}]}
    assert text_store.is_own_source(m, "weixin") is True
    # 开启检查时（默认）：判为自己发的，不产出正文
    assert text_store.body_of(m, {}, "weixin") == ""
    # 显式关闭检查后：来源不再影响取正文，内容照常产出
    assert text_store.body_of(m, {}, "weixin", check_own=False) != ""
