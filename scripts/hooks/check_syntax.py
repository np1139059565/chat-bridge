#!/usr/bin/env python3
"""pre-commit 语法校验钩子

对本次提交涉及的文件做基础语法校验，避免语法错误进入仓库：
- .json      → json.load
- .yaml/.yml → yaml.safe_load
- .py        → ast.parse（比 py_compile 更快，且不会产出 __pycache__）
- .js        → node --check

设计取舍：
- 只做「语法」校验，不做风格检查：风格问题交给 CI 的 lint 作业，
  避免提交被大量非阻断性提示打断。
- PyYAML / node 缺失时「跳过」而非报错：钩子不应把环境缺失误判为代码错误。

用法（由 pre-commit 调用，文件名以参数传入）：
    python scripts/hooks/check_syntax.py <文件1> <文件2> ...

退出码：0 = 全部通过；1 = 存在语法错误（详情打印到 stderr）。
"""
import ast
import json
import os
import shutil
import subprocess
import sys

# 扩展名 → 校验器名称（仅用于错误提示中的可读标签）
KIND_LABEL = {
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".py": "Python",
    ".js": "JavaScript",
}


def check_json(path):
    """校验 JSON 文件语法；通过返回 None，失败返回错误信息。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            json.load(fh)
        return None
    except Exception as e:
        return str(e)


def check_yaml(path):
    """校验 YAML 文件语法；未安装 PyYAML 时跳过（返回 None）。"""
    try:
        import yaml
    except ImportError:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            yaml.safe_load(fh)
        return None
    except Exception as e:
        return str(e)


def check_python(path):
    """校验 Python 文件语法；通过返回 None，失败返回带行号的错误信息。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            ast.parse(fh.read())
        return None
    except SyntaxError as e:
        return "%s（第 %s 行）" % (e.msg, e.lineno)
    except Exception as e:
        return str(e)


def _find_node():
    """查找可用的 node 可执行文件。

    顺序：环境变量 NODE_BIN → PATH → 本地便携安装目录。
    本工程允许把 node 便携版解压到 D:\\mydata\\tools 下而不进系统 PATH，
    故补充目录探测，避免「装了 node 却仍被跳过」。
    """
    import glob
    env = os.environ.get("NODE_BIN")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("node")
    if found:
        return found
    candidates = []
    for base in (r"D:\mydata\tools", os.path.join(os.path.expanduser("~"), "nodejs")):
        candidates += glob.glob(os.path.join(base, "node-*", "node.exe"))
    return sorted(candidates)[-1] if candidates else None


def _check_js_esprima(path):
    """用 esprima（纯 Python 解析器）校验 JS 语法；不可用时返回 None。

    作为 node 缺失时的兜底：把「环境无 node 就完全跳过 JS 校验」的盲区补上。
    只做语法解析（parseScript），不做风格检查。
    """
    try:
        import esprima
    except ImportError:
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            esprima.parseScript(fh.read())
        return None
    except Exception as e:
        return "esprima 解析失败：%s" % e


def check_js(path):
    """校验 JS 文件语法：优先 node --check，缺失时回退 esprima；都无则跳过。

    node 与 esprima 都不具备时才返回 None（跳过）——把「无 node 即无校验」
    的盲区收敛到「两者皆无」这一极端情况。
    """
    node = _find_node()
    if node:
        proc = subprocess.run([node, "--check", path], capture_output=True)
        if proc.returncode == 0:
            return None
        out = (proc.stderr or proc.stdout).decode("utf-8", "replace").strip()
        return out or "node --check 校验失败"
    # node 不可用：回退到 esprima（纯 Python）
    return _check_js_esprima(path)


# 扩展名 → 校验函数
DISPATCH = {
    ".json": check_json,
    ".yaml": check_yaml,
    ".yml": check_yaml,
    ".py": check_python,
    ".js": check_js,
}


def main(argv):
    """入口：逐个校验传入文件，收集全部失败项后统一输出。"""
    failed = []
    for path in argv:
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(path)[1].lower()
        checker = DISPATCH.get(ext)
        if checker is None:
            continue
        err = checker(path)
        if err:
            failed.append((path, KIND_LABEL.get(ext, ext), err))
    # 一次性打印全部失败项，便于一轮修完
    if not failed:
        return 0
    for path, kind, err in failed:
        print("[%s] %s\n    %s" % (kind, path, err), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
