"""AI 工具调用镜像插件 —— 路径基准（唯一来源）

集中定义服务端所有目录与文件的绝对路径，供各模块统一引用；
路径只在此处推导，文件搬迁或目录调整时只改这里。

位置约束：本文件必须始终位于 flask_server/ 根目录。
它靠 __file__ 推导「服务根」与「工程根」，是所有其它路径的锚点；
并在导入时把 core/ 与 tools/ 加入模块搜索路径，使既有扁平导入
（import tool_helpers、import external_tools 等）继续可用。
"""
import sys
from pathlib import Path

# 服务根目录（flask_server/）：本文件所在目录
APP_DIR = Path(__file__).resolve().parent
# 工程根目录：服务根的上一级
PROJECT_ROOT = APP_DIR.parent

# ---------- 服务内子目录 ----------
CORE_DIR = APP_DIR / "core"      # 核心支撑：错误分类、响应、YAML、配置、规则、卡片总线
TOOLS_DIR = APP_DIR / "tools"    # 工具实现与通用辅助
CONFIG_DIR = APP_DIR / "config"  # 配置文件（纯数据）
DATA_DIR = APP_DIR / "data"      # 运行时数据产物

# 引导：把核心与工具目录加入模块搜索路径。
# 既有代码全部是扁平导入（如 from tool_helpers import ...），
# 搬迁后靠这一步维持导入可用，避免改动大量 import 语句。
for _sub in (CORE_DIR, TOOLS_DIR):
    if _sub.is_dir() and str(_sub) not in sys.path:
        sys.path.insert(0, str(_sub))

# ---------- 配置文件 ----------
# 配置集中为两份：定义文件入库、跨机器共享（有哪些工具、有哪些指令、
# 站点映射等）；运行时文件排除出版本库（开关、端口、工具上下线等本机状态）。
# 这样改开关不会污染版本历史，新增指令又能正常入库。
# 两份文件内各含 app / custom_tools / bridge 三个分区，由各子系统各写各段。
# 读写统一走 core/config_file.py，路径只在此处定义一次。
#   definition.yaml —— 全部定义，入库（站点映射、工具定义、指令、选择器、主机地址）
#   runtime.yaml    —— 全部运行时与密钥，不入库（开关、端口、凭证、工具上下线）
DEFINITION_PATH = CONFIG_DIR / "definition.yaml"
RUNTIME_PATH = CONFIG_DIR / "runtime.yaml"

# ---------- 运行时数据 ----------
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
BRIDGE_STATE_PATH = DATA_DIR / "remote_bridge_state.json"
# 语音临时目录：QQ 语音解码后的 PCM/WAV、TTS 合成的音频文件都落这里；
# 属运行时产物，用后即删，不长期留存。
VOICE_DIR = DATA_DIR / "voice"
# QQ 图片目录：用户从 QQ 发来的图片存这里，供镜像扩展取走、贴进网页 AI 输入框。
QQ_IMAGES_DIR = DATA_DIR / "qq_images"
# 网页版机器人目录：网页版对话收件箱的存储与音频文件都落这里。
# 收件箱文件存对话消息（JSON）；音频目录存 TTS 合成的 MP3，供网页直接播放。
WEB_DIR = DATA_DIR / "web"
WEB_INBOX_PATH = WEB_DIR / "inbox.json"
WEB_AUDIO_DIR = WEB_DIR / "audio"
# 网页图片目录：指令结果的截图等存这里，供网页经接口读取展示。
WEB_IMAGES_DIR = WEB_DIR / "images"
# 记忆系统目录：结构化记忆数据库（消息树 + 蒸馏 + 事件层）落这里。
# 单一 SQLite 文件承载全部记忆，启动时加载进内存，供接口读写。
MEMORY_DB_DIR = DATA_DIR / "memory"
MEMORY_DB_PATH = MEMORY_DB_DIR / "memory.db"
# 桥接日志目录：按天一个文件，便于回溯运行轨迹（后端 print 默认只进终端，
# 不落盘；此处给桥接层一个持久化的日志落点）。
LOGS_DIR = DATA_DIR / "logs"

# ---------- 工程级目录 ----------
RULES_DIR = PROJECT_ROOT / "rules"
SKILLS_ROOT = PROJECT_ROOT / "skills"

# 供错误定位做前缀匹配用（字符串形式）
APP_DIR_STR = str(APP_DIR)
