"""标准 System Prompt 生成（任务 A-2）：GET /v1/system_prompt 的数据层。

内容边界（docs/split-mirror-and-tools-service.md 第 3.2 节）：
身份 + 规则 + 技能清单 + 「调用前先查参数」通则。

四段全部从既有模块读取，本模块不另设第二真源：
- 身份段：固定文字（工具服务自身定位，依据规格第一节「核心定位」）；
- 规则段：rules.list_rules() —— 只暴露规则名 + 读取优先级，不注入正文；
- 技能段：prompt_sections.sections() / .skills() —— 已上线口径，
  下线技能与指令执行端（kind=command_action）已被上游过滤；
- 通则段：固定文字 —— 调用任何工具前先用 get_tool_params 查准确参数名。

方言内容（工具调用格式、结果回传格式、朗读稿、网页选择器等场景词）
一律不进本文件：那是翻译员取回后追加的部分（规格 4.3 节）。
"""

import rules
import prompt_sections

# 分段标记：完整文本用它们分隔四段，也便于测试与调用方断言
MARK_IDENTITY = "【身份】"
MARK_RULES = "【规则】"
MARK_SKILLS = "【技能】"
MARK_PARAMS = "【调用前先查参数】"

_IDENTITY_TEXT = (
    "你是工具服务的对话端：负责理解客户端转来的用户请求，按本提示词中的"
    "规则与技能说明完成任务，需要外部能力时通过标准工具接口调用本地工具。"
    "你只与标准接口和工具结果打交道，不感知也不猜测客户端背后的具体场景。"
)

_PARAMS_TEXT = (
    "调用任何工具之前，必须先用 get_tool_params 查询该工具的准确参数名与"
    "取值要求，再按查询结果构造调用；不确定有哪些工具时先用 list_tools "
    "获取清单。不要凭记忆猜测参数名，也不要假设参数可选性。"
)


def identity_section():
    """身份段：工具服务自身定位，固定文字。"""
    return _IDENTITY_TEXT


def rules_section():
    """规则段：只列规则名 + 读取优先级；正文由 AI 按需 read_rule 读取。"""
    items = rules.list_rules()
    if not items:
        return "（当前没有规则。新增的规则会按其读取优先级出现在这里。）"
    lines = []
    for it in items:
        label = rules.PRIORITY_LABELS.get(it["priority"], it["priority"])
        lines.append("- %s（读取优先级：%s）" % (it["name"], label))
    return "\n".join(lines)


def _sections_text():
    """收集 prompt_sections 各段的非空说明文字。"""
    parts = []
    for s in prompt_sections.sections():
        text = (s.get("text") or "").strip()
        if text:
            parts.append(text)
    return parts


def _skills_listing():
    """把已上线技能拼成清单行：名称、摘要、工具。"""
    listing = []
    for s in prompt_sections.skills():
        row = "- %s" % s.get("name")
        if s.get("summary"):
            row += "：%s" % s["summary"]
        tools = "、".join(s.get("tools") or [])
        if tools:
            row += "（工具：%s）" % tools
        listing.append(row)
    return listing


def skills_section():
    """技能段：已上线技能的统一说明与清单（复用 prompt_sections 口径）。"""
    parts = _sections_text()
    listing = _skills_listing()
    if listing:
        parts.append("技能清单：\n" + "\n".join(listing))
    if not parts:
        return "（当前没有已上线的技能。）"
    return "\n\n".join(parts)


def params_section():
    """通则段：调用前先查参数。"""
    return _PARAMS_TEXT


def build_system_prompt():
    """聚合四段，返回 { system_prompt, sections }。

    system_prompt 为完整文本（分段标记 + 正文）；sections 记录各段
    标记与字符数，供调用方与测试断言，不重复携带正文。
    """
    body = [
        (MARK_IDENTITY, identity_section()),
        (MARK_RULES, rules_section()),
        (MARK_SKILLS, skills_section()),
        (MARK_PARAMS, params_section()),
    ]
    text_parts = []
    meta = []
    for mark, seg in body:
        seg = (seg or "").strip()
        text_parts.append(mark + "\n" + seg)
        meta.append({"mark": mark, "chars": len(seg)})
    return {
        "system_prompt": "\n\n".join(text_parts),
        "sections": meta,
    }
