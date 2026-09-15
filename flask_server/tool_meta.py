"""AI 工具调用镜像插件 —— 内置工具元数据

存放内置工具的声明（描述 + 参数表），供 tools_impl 组装为 TOOLS，
并由 /tools、get_tool_params 与 System Prompt 使用。

与 tools_impl 分离的原因：本文件是「声明」而非「实现」，内容稳定、
几乎不参与热重载；把实现文件留给 t_xxx 函数，可让 AI 自愈时面对的代码更聚焦。

字段约定（每个工具条目）：
- description：给 AI 看的功能说明，会写入 System Prompt，质量直接影响调用准确率
- parameters ：参数表，每项含 name / type / required / description
  - name      必须与 t_xxx 实现里 _require 校验的名字一致，否则会被判为缺参
  - type      仅用于展示与提示（string / integer / boolean / array）
  - required  为 True 时缺失该参数会抛 ToolParamError（归类 parameter）

维护提示：新增内置工具需同时改三处 ——
  1. 本文件的 TOOLS 声明
  2. tools_impl.py 的 t_xxx 实现
  3. tools_impl.py 末尾的 DISPATCH 派发表
"""

TOOLS = {
    # ---------- 文件系统类：目录浏览、文件检索、读写与删除 ----------
    "list_dir": {
        "description": "列出指定目录下的文件和子目录（不含点文件）",
        "parameters": [
            {"name": "target_directory", "type": "string", "required": True, "description": "要列出的目录路径（相对或绝对）"},
            {"name": "ignore_globs", "type": "array", "required": False, "description": "要忽略的通配符模式列表"},
        ],
    },
    "search_file": {
        "description": "按文件名通配符模式递归搜索文件，支持忽略特定模式",
        "parameters": [
            {"name": "target_directory", "type": "string", "required": True, "description": "搜索根目录"},
            {"name": "pattern", "type": "string", "required": True, "description": "文件名通配符，如 *.js"},
            {"name": "recursive", "type": "boolean", "required": False, "description": "是否递归子目录，默认 true"},
            {"name": "caseSensitive", "type": "boolean", "required": False, "description": "是否区分大小写"},
            {"name": "ignore_globs", "type": "array", "required": False, "description": "忽略模式列表"},
        ],
    },
    "search_content": {
        "description": "基于正则在文件内容中搜索匹配（支持上下文、类型过滤）",
        "parameters": [
            {"name": "pattern", "type": "string", "required": True, "description": "正则表达式"},
            {"name": "path", "type": "string", "required": False, "description": "搜索路径，默认当前目录"},
            {"name": "glob", "type": "string", "required": False, "description": "文件名过滤，如 *.py"},
            {"name": "contextAround", "type": "integer", "required": False, "description": "上下文字节数/行数"},
            {"name": "caseSensitive", "type": "boolean", "required": False, "description": "是否区分大小写"},
        ],
    },
    "read_file": {
        # 只接受绝对路径：不做「相对工程根」的隐式推导，避免调用方以为在项目内却读到别处
        "description": "读取本地文件内容（仅接受绝对路径），支持指定偏移与行数",
        "parameters": [
            {"name": "filePath", "type": "string", "required": True, "description": "文件绝对路径"},
            {"name": "offset", "type": "integer", "required": False, "description": "起始行（从 1 开始）"},
            {"name": "limit", "type": "integer", "required": False, "description": "读取行数"},
        ],
    },
    "read_skill": {
        # 专用通道：按 skill 名 + skill 内相对路径定位，替代传 skills/xxx/SKILL.md 的耦合做法
        "description": "读取某个 skill 目录下的文档（相对该 skill 目录的路径，如 SKILL.md）",
        "parameters": [
            {"name": "skill", "type": "string", "required": True, "description": "skill 名称（skills/ 下的目录名，如 debug_chrome）"},
            {"name": "file", "type": "string", "required": True, "description": "skill 目录内的相对路径，如 SKILL.md"},
            {"name": "offset", "type": "integer", "required": False, "description": "起始行（从 1 开始）"},
            {"name": "limit", "type": "integer", "required": False, "description": "读取行数"},
        ],
    },
    "read_lints": {
        # 本地服务未集成 linter：固定返回空诊断，保持接口形状一致
        "description": "读取工作区或指定文件的 linter 诊断信息（错误/警告）",
        "parameters": [
            {"name": "paths", "type": "array", "required": False, "description": "文件或目录路径"},
            {"name": "severity", "type": "array", "required": False, "description": "过滤严重级别"},
        ],
    },
    "replace_in_file": {
        # 要求 old_str 在文件中唯一，避免误改多处；适合最小化改动
        "description": "在已有文件中进行精确字符串替换（用于最小化改动）",
        "parameters": [
            {"name": "filePath", "type": "string", "required": True, "description": "文件路径"},
            {"name": "old_str", "type": "string", "required": True, "description": "待替换原文（须唯一）"},
            {"name": "new_str", "type": "string", "required": True, "description": "替换后的文本"},
        ],
    },
    "write_to_file": {
        # 覆盖写入：父目录不存在时自动创建，便于生成新文件
        "description": "创建或覆盖写入完整文件内容",
        "parameters": [
            {"name": "filePath", "type": "string", "required": True, "description": "文件路径"},
            {"name": "content", "type": "string", "required": True, "description": "完整文件内容"},
        ],
    },
    "delete_file": {
        "description": "删除指定路径的文件",
        "parameters": [
            {"name": "target_file", "type": "string", "required": True, "description": "要删除的文件路径"},
        ],
    },

    # ---------- 自描述类：让 AI 先查参数再调用，避免臆造参数名 ----------
    "get_tool_params": {
        "description": "根据工具 id 查询其参数、说明与用法",
        "parameters": [
            {"name": "tool_id", "type": "string", "required": True, "description": "工具名称/id"},
        ],
    },

    # ---------- 规则类：按需读取用户自定义约定（规则内容本身不写入 System Prompt） ----------
    "list_rules": {
        "description": "列出本机可用的规则文件（规则名 + 摘要），供 AI 判断该读取哪条规则",
        "parameters": [],
    },
    "read_rule": {
        "description": "按规则名读取某条规则的完整内容（如 self-healing 异常自愈规则）",
        "parameters": [
            {"name": "name", "type": "string", "required": True, "description": "规则名（不含扩展名），先用 list_rules 获取"},
        ],
    },

    # ---------- 执行类：按语言选择解释器执行命令，支持的语言由 config.yaml 决定 ----------
    "run_command": {
        "description": "执行本地命令（按指定脚本语言选择解释器；支持的语言由后端配置决定）",
        "parameters": [
            {"name": "language", "type": "string", "required": True, "description": "脚本语言类型，如 python / shell / cmd / powershell / git 等（以 get_tool_params 返回的支持列表为准）"},
            {"name": "command", "type": "string", "required": True, "description": "要执行的命令或代码块内容"},
            {"name": "cwd", "type": "string", "required": False, "description": "工作目录，默认使用当前工程目录"},
            {"name": "timeout", "type": "integer", "required": False, "description": "超时秒数，默认 60 秒"},
        ],
    },
}
