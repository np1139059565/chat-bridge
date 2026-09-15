"""
工程代码质量扫描脚本

用途：把本次重构走查使用的三类检查固化为可重复执行的脚本，纳入 CI。
输出三类问题清单：
  1. 超大文件（默认阈值 450 行）
  2. 超长 / 高圈复杂度函数（默认函数体 30 行、圈复杂度 10）
  3. 重复代码块（连续 5 行规范化后完全相同，且跨文件出现）

退出码：0 = 全部达标；1 = 存在超标项，便于 CI 中断。
用法：python scripts/check_quality.py [工程根目录]
"""
import ast
import collections
import os
import re
import sys

# 扫描时跳过的目录：第三方依赖、构建产物、缓存
SKIP_DIRS = {"__pycache__", "node_modules", ".git", "dist", "build", "out", "coverage", "vendor"}
# 参与扫描的源码扩展名
SOURCE_EXTS = (".py", ".js", ".css", ".html")
# 参与「重复代码」检测的扩展名：只针对代码。
# 原因：CSS 的属性组合在样式表中天然会重复（如不同作用域下的按钮基础样式），
# 这不构成「重复实现」缺陷；强行合并会改变层叠与作用域语义。
DUP_EXTS = (".py", ".js")
# 行数阈值：文件超过此值列入清单
FILE_LINE_LIMIT = 450
# 函数体行数阈值（不含空行与注释）
FUNC_LINE_LIMIT = 30
# 圈复杂度阈值
FUNC_CC_LIMIT = 10
# 重复块窗口大小（规范化后的连续行数）
DUP_WINDOW = 5

# 模块样板行：各分片文件统一采用的 IIFE 引导与命名空间声明。
# 这些行天然跨文件重复，属于「结构约定」而非「重复实现」，不纳入重复检查。
BOILERPLATE_LINES = {
    "(function () {",
    "'use strict';",
    'window.AIMirrorDialog = (function () {',
    'window.AIMirrorContent = (function () {',
    'const D = window.AIMirrorDialog;',
    'const A = window.AIMirrorContent;',
    'const M = D.methods;',
    'const h = Vue.h;',
    'const log = D.log;',
    'const hashStr = D.hashStr;',
    'const log = A.log;',
    'const A = window.AIMirrorContent;',
    'return D;',
    'return A;',
    '})();',
}


def is_boilerplate(line):
    """判断一行是否属于模块样板（用于从重复检查中排除）。"""
    return line in BOILERPLATE_LINES


def iter_files(root, exts=None):
    """遍历工程内源码文件，跳过 SKIP_DIRS。

    @param exts 限定扩展名元组；缺省用 SOURCE_EXTS（全部源码）
    """
    wanted = exts or SOURCE_EXTS
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if f.endswith(wanted):
                yield os.path.join(dirpath, f)


def read_lines(path):
    """读取文件全部行；读取失败返回空列表。"""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read().splitlines()
    except Exception:
        return []


def is_comment_or_blank(s):
    """判断一行是否为空行或纯注释行。"""
    t = s.strip()
    return (not t) or t.startswith("#") or t.startswith("//") or t.startswith("*") or t.startswith("/*")


def check_large_files(root):
    """检查一：文件总行数超过阈值。"""
    out = []
    for p in iter_files(root):
        lines = read_lines(p)
        if len(lines) > FILE_LINE_LIMIT:
            out.append((os.path.relpath(p, root), len(lines)))
    return sorted(out, key=lambda x: -x[1])


def cyclomatic(node):
    """计算 Python AST 节点的圈复杂度（分支 / 循环 / 布尔运算 / 异常处理各计 1）。"""
    n = 1
    for ch in ast.walk(node):
        if isinstance(ch, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.With, ast.AsyncWith, ast.IfExp, ast.Try)):
            n += 1
        elif isinstance(ch, ast.BoolOp):
            n += len(ch.values) - 1
        elif isinstance(ch, ast.comprehension):
            n += 1 + len(ch.ifs)
        elif isinstance(ch, ast.Match):
            n += len(ch.cases)
    return n


def _scan_py_file(p, root, out):
    """扫描单个 Python 文件，把超标的函数追加到 out。"""
    try:
        tree = ast.parse("\n".join(read_lines(p)))
    except SyntaxError:
        return
    rel = os.path.relpath(p, root)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        span = (node.end_lineno or node.lineno) - node.lineno + 1
        cc = cyclomatic(node)
        if span > FUNC_LINE_LIMIT or cc >= FUNC_CC_LIMIT:
            out.append((rel, node.name, node.lineno, span, cc))


def check_py_functions(root):
    """检查二：Python 函数体长度与圈复杂度超过阈值。"""
    out = []
    for p in iter_files(root):
        if p.endswith(".py"):
            _scan_py_file(p, root, out)
    return sorted(out, key=lambda x: -x[4])


def _normalize_lines(path):
    """读取文件并规范化为 (行号, 去空白文本) 列表。

    跳过空行、注释行与模块样板行；跳过样板行后窗口仍按剩余代码行的顺序拼接，
    因此跨样板的连续代码块依然可被识别。
    """
    norm = []
    for i, l in enumerate(read_lines(path), 1):
        if is_comment_or_blank(l):
            continue
        text = re.sub(r"\s+", " ", l.strip())
        if is_boilerplate(text):
            continue
        norm.append((i, text))
    return norm


def _index_windows(index, norm, rel):
    """把文件内每个滑动窗口登记到全局索引。"""
    for i in range(len(norm) - DUP_WINDOW + 1):
        key = tuple(x[1] for x in norm[i:i + DUP_WINDOW])
        # 窗口内容过短的不算重复（多为 import、单行赋值等）
        if sum(len(k) for k in key) < 80:
            continue
        index[key].append((rel, norm[i][0]))


def check_duplicates(root):
    """检查三：规范化后的连续 DUP_WINDOW 行在多处出现（仅针对代码文件）。"""
    index = collections.defaultdict(list)
    for p in iter_files(root, DUP_EXTS):
        _index_windows(index, _normalize_lines(p), os.path.relpath(p, root))
    # 只保留跨文件出现（同一文件内的重复另行评估）
    return [(places, key) for key, places in index.items()
            if len(places) >= 2 and len({pl[0] for pl in places}) >= 2]


def _report_large_files(root):
    """打印超大文件清单；有超标项返回 True。"""
    print("=" * 70)
    print("超大文件（阈值 %d 行）" % FILE_LINE_LIMIT)
    large = check_large_files(root)
    for rel, n in large:
        print("  %-50s %d 行" % (rel, n))
    if not large:
        print("  无")
    return bool(large)


def _report_functions(root):
    """打印超长 / 高圈复杂度函数清单；有超标项返回 True。"""
    print("=" * 70)
    print("超长 / 高圈复杂度函数（函数体 > %d 行 或 cc >= %d）" % (FUNC_LINE_LIMIT, FUNC_CC_LIMIT))
    funcs = check_py_functions(root)
    for rel, name, lineno, span, cc in funcs:
        print("  %-40s %-28s L%-5d 行数=%-5d cc=%d" % (rel, name, lineno, span, cc))
    if not funcs:
        print("  无")
    return bool(funcs)


def _report_duplicates(root):
    """打印重复代码块清单；有超标项返回 True。"""
    print("=" * 70)
    print("重复代码块（连续 %d 行，跨文件）" % DUP_WINDOW)
    dups = check_duplicates(root)
    for places, _key in dups:
        print("  出现在 %d 处：" % len(places))
        for rel, lineno in places:
            print("     %s  L%d" % (rel, lineno))
    if not dups:
        print("  无")
    return bool(dups)


def main():
    """入口：依次执行三类检查并输出结论；存在任一超标项时返回 1。"""
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 三类检查都执行完再汇总（避免短路导致报告不完整）
    has_large = _report_large_files(root)
    has_funcs = _report_functions(root)
    has_dups = _report_duplicates(root)
    failed = has_large or has_funcs or has_dups
    print("=" * 70)
    print("结论：" + ("存在超标项" if failed else "全部达标"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
