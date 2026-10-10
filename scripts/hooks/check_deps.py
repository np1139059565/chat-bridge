#!/usr/bin/env python3
"""pre-commit 依赖漂移校验钩子

目的：防止「代码里 import 了第三方库，却忘了写进 requirements.txt」——
这类遗漏在开发机上因已装库而不报错，换新机器才爆发（曾因漏 numpy 导致
新电脑启动失败）。本钩子把这类遗漏挡在提交前。

做法：
  1. 递归扫描 flask_server/**/*.py，用 AST 收集所有顶层 import（含 from ... import）。
  2. 排除标准库（sys.stdlib_module_names）与本地模块（flask_server 下的包 / 模块）。
  3. 剩下的即第三方 import 名，映射为规范包标识后，与 requirements.txt 声明比对。
  4. 代码用到、但 requirements 未声明的，判为漂移，拦截提交。

边界说明：
  - 只做「使用 → 声明」单向检查：代码里 import 了就必须声明。
    反向（声明了但没用到）不检查——可选依赖常用字符串惰性导入，
    AST 看不到，反向检查会误报。
  - import 名与 pip 包名不一致的（yaml / websocket / edge_tts 等）由别名表兜底。

用法（由 pre-commit 调用，全量扫描）：
    python scripts/hooks/check_deps.py

退出码：0 = 通过；1 = 存在未声明的第三方依赖（详情打印到 stderr）。
"""
import ast
import os
import re
import sys

# 仓库根：本脚本位于 scripts/hooks/ 下，向上两级
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 扫描范围：服务端代码
SCAN_DIR = os.path.join(ROOT, "flask_server")
# 依赖清单
REQ_FILE = os.path.join(SCAN_DIR, "requirements.txt")

# import 名 → 规范包标识 的别名表（仅收 import 名与 pip 名不一致的常见项）
IMPORT_ALIAS = {
    "yaml": "pyyaml",
    "websocket": "websocketclient",
    "edge_tts": "edgetts",
    "pil": "pillow",
    "cv2": "opencvpython",
    "bs4": "beautifulsoup4",
    "sklearn": "scikitlearn",
    "dotenv": "pythondotenv",
    "dateutil": "pythondateutil",
}

# requirements 行首包名：字母数字与 . _ -
_PKG_RE = re.compile(r"^([A-Za-z0-9_.\-]+)")


def norm(name):
    """包名归一化：小写并去掉 - 与 _，便于跨写法比对。"""
    return name.lower().replace("-", "").replace("_", "")


def import_to_id(mod):
    """把 import 名映射为规范包标识（先查别名，再归一化）。"""
    return IMPORT_ALIAS.get(mod, norm(mod))


def collect_declared():
    """解析 requirements.txt，返回已声明包的规范标识集合。

    跳过空行、注释行；每行取行首包名（忽略版本约束与环境标记）。
    """
    declared = set()
    if not os.path.isfile(REQ_FILE):
        return declared
    with open(REQ_FILE, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _PKG_RE.match(line)
            if m:
                declared.add(norm(m.group(1)))
    return declared


def collect_local_modules():
    """收集 flask_server 下的本地模块 / 包名（顶层 import 名口径）。

    含：所有 .py 文件名（去扩展名）、所有含 __init__.py 的目录名（包）。
    """
    local = set()
    for dirpath, dirnames, filenames in os.walk(SCAN_DIR):
        if "__pycache__" in dirpath:
            continue
        # 目录是包（含 __init__.py）→ 目录名即导入名
        if "__init__.py" in filenames:
            local.add(os.path.basename(dirpath))
        # 每个模块文件 → 文件名即导入名
        for f in filenames:
            if f.endswith(".py"):
                local.add(f[:-3])
    return local


def file_imports(path):
    """解析单个 .py，返回其顶层 import 的模块名列表。

    只收绝对导入（level==0）；相对导入天然是本地，忽略。
    语法错误的文件返回空列表（语法钩子会另行拦截）。
    """
    try:
        tree = ast.parse(open(path, "r", encoding="utf-8", errors="ignore").read())
    except Exception:
        return []
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module.split(".")[0])
    return names


def iter_py_files():
    """遍历 flask_server 下所有 .py 文件，产出其绝对路径（跳过 __pycache__）。"""
    for dirpath, _dirnames, filenames in os.walk(SCAN_DIR):
        if "__pycache__" in dirpath:
            continue
        for f in filenames:
            if f.endswith(".py"):
                yield os.path.join(dirpath, f)


def collect_imports():
    """扫描所有 .py 的顶层 import，返回 {import名: 首个出现的相对文件}。"""
    found = {}
    for path in iter_py_files():
        rel = os.path.relpath(path, ROOT)
        for n in file_imports(path):
            found.setdefault(n, rel)
    return found


def main():
    """入口：比对「代码用到的第三方」与「requirements 声明的」，报告差异。"""
    declared = collect_declared()
    local = collect_local_modules()
    imports = collect_imports()
    stdlib = set(sys.stdlib_module_names)

    missing = []
    for mod, where in sorted(imports.items()):
        if mod in stdlib or mod in local:
            continue  # 标准库 / 本地模块，无需声明
        if import_to_id(mod) not in declared:
            missing.append((mod, where))

    if not missing:
        return 0
    print("以下第三方依赖被 import，但未写入 flask_server/requirements.txt：", file=sys.stderr)
    for mod, where in missing:
        print("  %-16s （首个出现：%s）" % (mod, where), file=sys.stderr)
    print("请在 requirements.txt 补上对应包后重试。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
