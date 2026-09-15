"""自定义工具（来自标准 skill）—— 包入口

对外保持与原 custom_tools.py 完全一致的函数名与语义，调用方（server / routes）
无需改动导入方式（`import custom_tools as ct` 后 `ct.load_tools()` 等仍然可用）。

子模块划分：
- paths.py     路径基准与常量
- loader.py    custom_tools.yaml 与 tool.json 的解析、命令拼装辅助
- registry.py  注册表读写、安装/删除/更新、本地执行
- meta.py      对外视图（provider 分组、说明段落、元数据）
- scan.py      目录扫描
"""
# 路径与常量
from .paths import (
    APP_DIR, PROJECT_ROOT, CT_PATH, NAME_RE,
    DEFAULT_SKILL_ROOTS, to_project_rel, resolve_to_abs, default_roots,
)

# 解析层
from .loader import (
    strip_comment, parse_scalar, quote, parse_yaml, dump_yaml,
    infer_interpreter, to_str, flag_arg, parse_skill,
)

# 注册表与执行
from .registry import (
    load_tools, save_tools, install, remove, update,
    get_tool, is_enabled, run,
)

# 对外视图
from .meta import (
    external_providers, prompt_sections, public_meta, all_meta, all_meta_full,
)

# 扫描
from .scan import scan_dir
