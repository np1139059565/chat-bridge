"""
AI 工具调用镜像插件 —— 运行时全局状态中心

本模块集中持有服务运行期需要跨模块共享的可变状态，供路由、错误分类
等模块统一读写，避免各模块之间相互 import 造成循环依赖：

- app           Flask 应用实例
- impl          当前生效的工具实现模块
- TOOLS         当前可用的工具元数据（内置）
- DISPATCH      工具名 → 可调用函数
- CONFIG        当前生效的配置（来自 config/ 下两份配置文件的合并）

注意：这些变量在初始化阶段被赋值，因此其它模块必须通过 `runtime.XXX` 访问，
不能在导入期 `from runtime import TOOLS`，否则拿到的是旧引用。
"""
import sys
from pathlib import Path

from flask import Flask

# 当前文件所在目录（flask_server/）：作为导入引导，先确保 paths 可被导入，
# 再由 paths 统一推导其余路径并把 core/ tools/ 加入模块搜索路径。
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import paths

APP_DIR_STR = paths.APP_DIR_STR

# Flask 应用实例；路由模块通过蓝图注册到这里
app = Flask(__name__)

# 当前生效的工具实现模块；由 app.py 的 _init_runtime() 在初始化阶段注入 tools_impl
impl = None


# 配置唯一来源：本地 config/ 下的两份文件（插件从后端读取，不存浏览器）
# definition.yaml 存定义（入库），runtime.yaml 存运行时字段（端口、工具上下线、语言清单，不入库）
# 具体读写与路径见 core/config_file.py。
CONFIG = {"flask": {"host": "127.0.0.1", "port": 5000},
          "limits": {"max_json_chars": 100000},
          "default_profile": "glm", "site_profiles": {}, "tools": {}}

# 工具表：初始化阶段由 app.py 的 _init_runtime() 用 tools_impl 填充
TOOLS = {}
DISPATCH = {}

# 错误分类提示语：告诉 AI 该「改参数重试」还是「改工具代码」
HINTS = {
    "parameter": "这是调用参数问题（缺失 / 类型不符 / 取值非法），不是工具代码缺陷。"
                 "请核对参数名与取值后重试，不要修改工具代码。",
    "environment": "这是运行环境或路径问题（文件不存在、权限不足、路径非法等）。"
                   "请确认路径与权限后重试。",
    "tool_internal": "这是本地工具代码自身的缺陷（异常发生在工具实现内部），"
                     "反复调整参数无法解决。请把错误信息与堆栈反馈给维护者检查工具实现。",
    "unknown_tool": "工具名不存在，请从工具目录中选择正确的名称后重试。",
    "disabled": "该工具已被管理员下线（在配置中 disabled）。请改用其它可用工具，"
                "或上线该工具后重试；仅靠调整参数无法使其恢复。",
}

# 错误分类的中文标签
ORIGIN_LABEL = {
    "parameter": "parameter（参数问题）",
    "environment": "environment（环境/路径问题）",
    "tool_internal": "tool_internal（工具代码缺陷）",
    "unknown_tool": "unknown_tool（工具名错误）",
    "disabled": "disabled（工具已下线）",
}


def is_tool_enabled(name):
    """判断工具当前是否上线；未配置的工具默认在线。"""
    entry = CONFIG.get("tools", {}).get(name)
    if not entry:
        return True
    return bool(entry.get("enabled", True))


def refresh_external_providers():
    """把【已上线】的 executor=external 工具按 provider 注册到提供方注册表。

    同步移除已不存在或不含已上线工具的提供方，避免下线后仍保留旧定义。
    """
    import custom_tools as ct
    import external_tools
    try:
        groups = ct.external_providers()
    except Exception as e:
        print("[ext] 读取外部工具失败：", e)
        return
    external_tools.hub.replace_providers(groups)
