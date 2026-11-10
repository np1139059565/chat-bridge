"""AI 工具调用镜像插件 —— 内置工具元数据

存放内置工具的声明（描述 + 参数表），供 tools_impl 组装为 TOOLS，
并由 /tools、get_tool_params 与 System Prompt 使用。

与 tools_impl 分离的原因：本文件是「声明」而非「实现」，内容稳定；
实现文件只保留 t_xxx 函数，声明与实现各自独立、职责边界清晰。

字段约定（每个工具条目）：
- description：给 AI 看的功能说明，会写入 System Prompt，质量直接影响调用准确率
- parameters ：标准 JSON Schema 对象，形如 {"type": "object", "properties": {...}, "required": [...]}
  - properties 的键即参数名，必须与 t_xxx 实现里 _require 校验的名字一致，否则会被判为缺参
  - 属性内的 type 仅用于展示与提示（string / integer / boolean / array）
  - 联合类型用 anyOf 表达（全库仅 read_file 的 path 一处，依据 split-mirror 决策 8）
  - 顶层 required 数组列出全部必填参数名；缺失必填参数会抛 ToolParamError（归类 parameter）
  - 无参数工具为 {"type": "object", "properties": {}}

历史格式（数组，每项含 name / type / required 布尔 / description）已于阶段 1b
迁移为标准 schema；双格式读取的兼容辅助见 tools/tool_param_check.py，
skill 侧 tool.json 的解析兼容见 custom_tools/loader.py。

维护提示：新增内置工具需同时改三处 ——
  1. 本文件的 TOOLS 声明
  2. tools_impl.py 的 t_xxx 实现
  3. tools_impl.py 末尾的 DISPATCH 派发表
"""

TOOLS = {
    # ---------- 自描述类：让 AI 先查参数再调用，避免臆造参数名 ----------
    "list_tools": {
        "description": "列出当前可调用的全部工具（名称 + 说明 + 是否含参数），供发现有哪些工具可用；"
                       "需查某个工具的参数时再用 get_tool_params",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_tool_params": {
        "description": "根据工具 id 查询其参数、说明与用法",
        "parameters": {
            "type": "object",
            "properties": {
                "tool_id": {"type": "string", "description": "工具名称/id"},
            },
            "required": ["tool_id"],
        },
    },

    # ---------- 文件系统类：目录浏览、文件检索、读写与删除 ----------
    "list_dir": {
        "description": "列出指定目录下的文件和子目录（不含点文件）",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要列出的目录路径（相对或绝对）"},
                "ignore_globs": {"type": "array", "description": "要忽略的通配符模式列表"},
            },
            "required": ["path"],
        },
    },
    "search_file": {
        "description": "按文件名通配符模式递归搜索文件，支持忽略特定模式",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "搜索根目录"},
                "glob": {"type": "string", "description": "文件名通配符，如 *.js；匹配不区分大小写"},
                "recursive": {"type": "boolean", "description": "是否递归子目录，默认 true"},
                "ignore_globs": {"type": "array", "description": "忽略模式列表，同样不区分大小写"},
            },
            "required": ["path", "glob"],
        },
    },
    "search_content": {
        "description": "基于正则在文件内容中搜索匹配（支持上下文、类型过滤）",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "正则表达式（内容匹配）"},
                "path": {"type": "string", "description": "搜索路径，默认当前目录"},
                "glob": {"type": "string", "description": "文件名过滤，如 *.py"},
                "context_around": {"type": "integer", "description": "上下文字节数/行数"},
                "case_sensitive": {"type": "boolean", "description": "是否区分大小写"},
            },
            "required": ["pattern"],
        },
    },
    "read_file": {
        # 路径口径与写文件类工具一致：绝对路径原样，相对路径以工程根为基准。
        # 正文超过内联阈值时结果改为 file_ref 引用，正文由前端取回后粘贴进对话。
        "description": "读取本地文件内容（绝对路径原样，相对路径以工程根为基准），支持指定偏移与行数，支持一次读取多个文件",
        "parameters": {
            "type": "object",
            "properties": {
                # 联合类型（决策 8）：传字符串读一个文件，传数组一次读多个（上限 20）
                "path": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}, "maxItems": 20},
                    ],
                    "description": "文件路径；传字符串读一个文件，传数组一次读多个（最多 20 个）",
                },
                "offset": {"type": "integer", "description": "起始行（从 1 开始）"},
                "limit": {"type": "integer", "description": "读取行数"},
            },
            "required": ["path"],
        },
    },
    "read_image": {
        # 结果结构与 get_page_snapshot 对齐：图片经现有截图粘贴链路进网页 AI，
        # 正文只带精简标记，不把图片二进制写进对话
        "description": "读取本地图片文件并贴入网页 AI 输入框（支持 png/jpg/jpeg/gif/webp/bmp，单张上限 10MB）",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "图片路径（绝对路径原样，相对路径以工程根为基准）"},
            },
            "required": ["path"],
        },
    },
    "push_file": {
        # 交付类工具：把电脑上的文件推到用户手机，让用户能直接下载。
        # 目前只放行压缩包与 Markdown 文档，避免误推敏感或可执行文件。
        "description": "把电脑上的文件推送到用户手机 QQ，供其下载（当前支持 .zip 压缩包与 .md 文档）",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要推送的文件路径（绝对路径原样，相对路径以工程根为基准）"},
            },
            "required": ["path"],
        },
    },
    "list_skills": {
        "description": "列出本机可用的 skill（名称 + 摘要），供 AI 判断该读取哪个技能文档",
        "parameters": {"type": "object", "properties": {}},
    },
    "read_skill": {
        # 专用通道：按 skill 名 + skill 内相对路径定位，替代传 skills/xxx/SKILL.md 的耦合做法
        "description": "读取某个 skill 目录下的文档（相对该 skill 目录的路径，如 SKILL.md）",
        "parameters": {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "description": "skill 名称（skills/ 下的目录名，如 debug_chrome）"},
                "path": {"type": "string", "description": "skill 目录内的相对路径，如 SKILL.md"},
                "offset": {"type": "integer", "description": "起始行（从 1 开始）"},
                "limit": {"type": "integer", "description": "读取行数"},
            },
            "required": ["skill", "path"],
        },
    },
    "read_lints": {
        # 本地服务未集成 linter：固定返回空诊断，保持接口形状一致
        "description": "读取工作区或指定文件的 linter 诊断信息（错误/警告）",
        "parameters": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "description": "文件或目录路径"},
                "severity": {"type": "array", "description": "过滤严重级别"},
            },
        },
    },
    "replace_in_file": {
        # 要求 old_string 在文件中唯一，避免误改多处；适合最小化改动
        "description": "在已有文件中进行精确字符串替换（用于最小化改动）",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "old_string": {"type": "string", "description": "待替换原文（须唯一）"},
                "new_string": {"type": "string", "description": "替换后的文本"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    "write_to_file": {
        # 覆盖写入：父目录不存在时自动创建，便于生成新文件
        "description": "创建或覆盖写入完整文件内容",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "完整文件内容"},
            },
            "required": ["path", "content"],
        },
    },
    "delete_file": {
        "description": "删除指定路径的文件",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要删除的文件路径"},
            },
            "required": ["path"],
        },
    },

    # ---------- 规则类：按需读取用户自定义约定（规则内容本身不写入 System Prompt） ----------
    "list_rules": {
        "description": "列出本机可用的规则文件（规则名 + 摘要），供 AI 判断该读取哪条规则",
        "parameters": {"type": "object", "properties": {}},
    },
    "read_rule": {
        "description": "按规则名读取某条规则的完整内容",
        "parameters": {
            "type": "object",
            "properties": {
                "rule": {"type": "string", "description": "规则名（不含扩展名），先用 list_rules 获取"},
            },
            "required": ["rule"],
        },
    },

    # ---------- 执行类：按语言选择解释器执行命令，支持的语言由 runtime.yaml 决定 ----------
    "run_command": {
        "description": "执行本地命令（按指定脚本语言选择解释器；支持的语言由后端配置决定）",
        "parameters": {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "description": "脚本语言类型，如 python / shell / cmd / powershell / git 等"
                                   "（以 get_tool_params 返回的支持列表为准）",
                },
                "command": {"type": "string", "description": "要执行的命令或代码块内容"},
                "cwd": {"type": "string", "description": "工作目录，默认使用当前工程目录"},
                "timeout": {"type": "integer", "description": "超时秒数，默认 45 秒"},
                "async": {
                    "type": "boolean",
                    "description": "异步执行：true 时立即返回 task_id，命令在后台运行；"
                                   "随后用 get_tool_params 里的 command_task 工具或 GET /tool/command_task 轮询结果。"
                                   "适合预计耗时较长、不想让调用方干等的命令",
                },
            },
            "required": ["language", "command"],
        },
    },

    # ---------- 执行类：查询 run_command 异步任务的状态与结果 ----------
    "command_task": {
        "description": "查询 run_command 异步任务的状态与结果：传入 task_id，返回 pending/running/done/failed 及结果",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "run_command 异步调用返回的任务号"},
            },
            "required": ["task_id"],
        },
    },

    # ---------- 记忆类：回查历史记忆（结构化记忆系统的读取侧入口） ----------
    "memory_search": {
        # 没有这个工具，AI 只能「写」记忆、无法「读」记忆，记忆库沦为死数据。
        "description": "检索历史记忆：传入当前任务或问题原文，返回相关的历史记忆节点（供回忆用户说过什么、之前怎么解决同类问题）",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "查询原文（当前任务/问题），同时作为关键词锚定基准"},
                "keywords": {"type": "array", "description": "检索关键词；不传则自动从 query 提取"},
                "focus": {"type": "string", "description": "排序焦点：relevance（相关度，默认）/ time（时间新）/ strength（强度高）"},
                "limit": {"type": "integer", "description": "返回条数，默认 10，上限 50"},
            },
            "required": ["query"],
        },
    },
    "memory_inspect": {
        # 抽检过往记忆的蒸馏质量：返回「原文 vs 蒸馏精华/关键词」对照，供 AI 判断是否失真。
        "description": "抽检记忆的蒸馏质量：返回指定节点（或某会话最近节点）的原文与蒸馏精华/关键词对照，供判断蒸馏是否失真、关键词是否有效",
        "parameters": {
            "type": "object",
            "properties": {
                "node_ids": {"type": "array", "description": "要抽检的节点 id 列表（整数）；不传则按 conv_id 或全库取最近节点"},
                "conv_id": {"type": "string", "description": "按会话取最近节点抽检（未给 node_ids 时生效）"},
                "limit": {"type": "integer", "description": "未给 node_ids 时，抽检最近多少个节点，默认 5，上限 20"},
            },
        },
    },
    "memory_refine": {
        # 修正蒸馏结果：AI 抽检发现偏差大时，直接改写该节点的精华与关键词。
        "description": "修正某节点的蒸馏结果：改写其精华与关键词（原始内容不动），用于蒸馏失真时纠正",
        "parameters": {
            "type": "object",
            "properties": {
                "node_id": {"type": "integer", "description": "要修正的节点 id"},
                "essence": {"type": "string", "description": "修正后的精华文本（与 keywords 至少提供一个）"},
                "keywords": {"type": "array", "description": "修正后的关键词列表"},
            },
            "required": ["node_id"],
        },
    },
}
