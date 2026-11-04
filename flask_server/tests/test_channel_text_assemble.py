"""正文组装（channel.text._assemble_ordered）行为测试

为什么需要：
    它是三条通道共用的正文组装逻辑，圈复杂度曾达 31——思考、正文、
    工具调用、语音四类内容各走一条分支，还要处理开关与空内容。
    这种函数一旦拆分出错，表现是「某类内容悄悄消失」，不会报错。
    故先把四类内容各自的出现与抑制条件钉死。

覆盖内容：
    - 思考块受开关控制，关闭时不出现
    - 工具调用只报工具名，不带参数
    - 语音块取 JSON 里的文字
    - 纯工具调用消息不产出正文
    - Markdown 原文在无思考无工具时直接采用
    - 输出顺序固定为 思考 → 正文 → 工具 → 语音

运行：python -m pytest tests/test_channel_text_assemble.py -q
"""
import json

from remote_bridge.channel import text as text_store


def _json_block(obj):
    """造一个代码块，内容是 JSON 字符串。

    @param obj 要序列化的对象
    @returns 内容块字典
    """
    return {"type": "code", "text": json.dumps(obj, ensure_ascii=False)}


def _para(t):
    """造一个普通段落块。

    @param t 段落文本
    @returns 内容块字典
    """
    return {"type": "paragraph", "text": t}


class TestThinking:
    """思考块。"""

    def test_thinking_kept_when_enabled(self):
        """开关打开时，思考内容以代码块形式出现。"""
        m = {"blocks": [{"type": "thinking", "text": "我在想"}]}
        out = text_store._assemble_ordered(m, {"thinking": True}, False)
        assert "我在想" in out
        # 用代码块包裹，等效于折叠
        assert "```" in out

    def test_thinking_dropped_when_disabled(self):
        """开关关闭时，思考内容不出现。"""
        m = {"blocks": [{"type": "thinking", "text": "我在想"}, _para("答案")]}
        out = text_store._assemble_ordered(m, {"thinking": False}, False)
        assert "我在想" not in out
        assert "答案" in out


class TestToolCall:
    """工具调用块。"""

    def test_tool_reports_name_only(self):
        """工具调用只报工具名，不带参数。"""
        m = {"blocks": [
            _para("让我查一下"),
            _json_block({"type": "bridge-chat-call", "tool": "search_file",
                         "parameters": {"path": "secret"}}),
        ]}
        out = text_store._assemble_ordered(m, {}, False)
        assert "search_file" in out
        # 参数不该出现在正文里
        assert "secret" not in out

    def test_pure_tool_call_yields_empty(self):
        """纯工具调用消息不产出正文。"""
        m = {"blocks": [_json_block({"type": "bridge-chat-call", "tool": "x"})]}
        assert text_store._assemble_ordered(m, {}, False) == ""


class TestVoice:
    """语音块。"""

    def test_voice_text_extracted(self):
        """语音块取 JSON 里的文字，排在正文之后。"""
        m = {"blocks": [
            _para("正文"),
            _json_block({"type": "bridge-voice", "text": "朗读内容"}),
        ]}
        out = text_store._assemble_ordered(m, {}, False)
        assert "朗读内容" in out
        # 语音排在正文之后
        assert out.index("正文") < out.index("朗读内容")


class TestMarkdownShortcut:
    """Markdown 原文快捷路径。"""

    def test_md_used_when_clean(self):
        """无思考无工具块时，直接采用 Markdown 原文。"""
        m = {"md": "# 标题\n正文", "blocks": [_para("正文")]}
        out = text_store._assemble_ordered(m, {}, True)
        # 原文的井号被保留
        assert "# 标题" in out

    def test_md_skipped_when_tool_present(self):
        """有工具调用块时不走快捷路径，否则工具痕迹会丢。

        注意：纯工具调用消息本就不产出正文（无可读内容），
        故这里配一个正文段落，才能观察工具名是否被保留。
        """
        m = {"md": "正文",
             "blocks": [_para("正文"),
                        _json_block({"type": "bridge-chat-call", "tool": "t1"})]}
        out = text_store._assemble_ordered(m, {}, True)
        # 工具名应出现，说明走了完整组装而非 Markdown 快捷路径
        assert "t1" in out

    def test_md_ignored_when_disabled(self):
        """use_md 为 False 时不采用原文。"""
        m = {"md": "# 标题", "blocks": [_para("纯文本")]}
        out = text_store._assemble_ordered(m, {}, False)
        assert "# 标题" not in out
        assert "纯文本" in out


class TestOrder:
    """四类内容的输出顺序。"""

    def test_full_order(self):
        """思考 → 正文 → 工具 → 语音。"""
        m = {"blocks": [
            _json_block({"type": "bridge-voice", "text": "语音段"}),
            _json_block({"type": "bridge-chat-call", "tool": "工具段"}),
            _para("正文段"),
            {"type": "thinking", "text": "思考段"},
        ]}
        out = text_store._assemble_ordered(m, {"thinking": True}, False)
        # 顺序固定，与块的物理顺序无关
        assert out.index("思考段") < out.index("正文段")
        assert out.index("正文段") < out.index("工具段")
        assert out.index("工具段") < out.index("语音段")
