"""技能说明段落：收集各技能向 System Prompt 注入的统一说明。

说明来自技能 tool.json 顶层的 prompt 字段；收集逻辑依附于自定义工具加载，
本模块只做对外暴露，供路由与前端调用。
"""
import custom_tools as ct


def sections():
    """返回已上线技能的统一说明列表：[ { skill, text } ]。"""
    return ct.prompt_sections()
