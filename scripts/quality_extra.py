"""工程质量检查 —— 三项基础检查（并入统一闸门）

本模块原本是 check_quality.py 的全部内容，现迁出，供 quality_rules.py 统一调用。
拆分的理由：两个脚本各自为政——提交钩子跑 quality_rules（九项），CI 跑 check_quality（三项），
口径不一致，CI 那道门还设了 continue-on-error，等于不设防。
统一为一个入口后，钩子与 CI 跑同一套规则，红绿才有意义。

三项检查：
  1. 超大文件           —— 文件总行数超阈值
  2. 超长 / 高复杂度函数 —— Python 函数体行数与圈复杂度
  3. 重复代码块         —— 连续若干行规范化后跨文件重复

返回结构各不相同，报告格式化由 quality_rules 按检查项分派。
"""
import ast
import collections
import os
import re

import qcommon

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

# 基础函数统一来自 qcommon；此处取局部别名，保持调用写法简短。
iter_files = qcommon.iter_files
read_lines = qcommon.read_lines
is_comment_or_blank = qcommon.is_comment_or_blank
cyclomatic = qcommon.cyclomatic
is_exempt = qcommon.is_exempt


def is_boilerplate(line):
    """判断一行是否属于模块样板（用于从重复检查中排除）。"""
    return line in BOILERPLATE_LINES


def _iter_targets(root, exts=None):
    """遍历参与检查的文件，剔除豁免清单中的第三方产物与生成副本。

    豁免规则由 qcommon.is_exempt 统一维护，此处只负责应用。
    @param root 工程根目录
    @param exts 限定扩展名元组；缺省沿用 qcommon 的源码扩展名
    @returns 逐个产出未被豁免的文件绝对路径
    """
    for p in iter_files(root, exts):
        rel = os.path.relpath(p, root)
        if is_exempt(rel):
            continue
        yield p


def check_large_files(root):
    """检查：文件总行数超过阈值。

    @returns [(相对路径, 行数)]，按行数降序
    """
    out = []
    for p in _iter_targets(root):
        n = len(read_lines(p))
        if n > FILE_LINE_LIMIT:
            out.append((os.path.relpath(p, root), n))
    return sorted(out, key=lambda x: -x[1])


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
    """检查：Python 函数体长度与圈复杂度超过阈值。

    @returns [(相对路径, 函数名, 行号, 行数, 圈复杂度)]，按圈复杂度降序
    """
    out = []
    for p in _iter_targets(root):
        if p.endswith(".py"):
            _scan_py_file(p, root, out)
    return sorted(out, key=lambda x: -x[4])


def _is_import_line(text):
    """判断一行是否属于导入区样板（导入语句或路径引导语句）。

    路径引导（sys.path.insert）与导入语句成对出现、内容固定，
    各模块的导入区因此天然相似，同样不应计入重复。
    @param text 已规范化的行文本
    @returns 属导入区样板时返回 True
    """
    return (text.startswith("import ") or text.startswith("from ")
            or text.startswith("sys.path.insert"))


def _normalize_lines(path):
    """读取文件并规范化为 (行号, 去空白文本, 是否导入区) 列表。

    跳过空行、注释行与模块样板行；跳过样板行后窗口仍按剩余代码行的顺序拼接，
    因此跨样板的连续代码块依然可被识别。

    第三个元素标记该行是否属于导入区。多行导入（from x import ( ... )）的续行
    本身不以 import / from 开头，仅看单行无法识别，故用括号配平跟踪导入区范围。
    各模块导入同一批依赖是「依赖相同」而非「实现重复」，不应据此要求合并。
    """
    norm = []
    in_import = False   # 当前是否处于多行导入的括号内
    depth = 0           # 导入区未闭合的括号层数
    for i, l in enumerate(read_lines(path), 1):
        if is_comment_or_blank(l):
            continue
        text = re.sub(r"\s+", " ", l.strip())
        if is_boilerplate(text):
            continue
        # 该行是否算导入区：本行是导入语句，或仍在上一条多行导入的括号内
        head = _is_import_line(text)
        is_imp = head or in_import
        # 维护括号配平：只有进入导入区后才需要跟踪续行
        if head or in_import:
            depth += text.count("(") - text.count(")")
            in_import = depth > 0
        norm.append((i, text, is_imp))
    return norm


def _index_windows(index, norm, rel):
    """把文件内每个滑动窗口登记到全局索引。"""
    for i in range(len(norm) - DUP_WINDOW + 1):
        win = norm[i:i + DUP_WINDOW]
        key = tuple(x[1] for x in win)
        # 窗口内容过短的不算重复（多为 import、单行赋值等）
        if sum(len(k) for k in key) < 80:
            continue
        # 整窗都属导入区的不算重复：各模块的导入区天然相似，
        # 反映的是「依赖相同」而非「实现重复」，不应据此要求合并。
        # 判据取规范化时算好的第三项，能覆盖多行导入的续行。
        if all(x[2] for x in win):
            continue
        index[key].append((rel, norm[i][0]))


def check_duplicates(root):
    """检查：规范化后的连续 DUP_WINDOW 行在多处出现（仅针对代码文件）。

    @returns [([(相对路径, 行号), ...], 窗口键)]，每组至少跨两个文件
    """
    index = collections.defaultdict(list)
    for p in _iter_targets(root, qcommon.DUP_EXTS):
        rel = os.path.relpath(p, root)
        # 同步生成的副本跳过：内容刻意与真源一致，不参与重复统计
        if qcommon.is_dup_exempt(rel):
            continue
        _index_windows(index, _normalize_lines(p), rel)
    # 只保留跨文件出现（同一文件内的重复另行评估）
    return [(places, key) for key, places in index.items()
            if len(places) >= 2 and len({pl[0] for pl in places}) >= 2]


def fmt_large_files(r):
    """超大文件条目的单行格式化。"""
    return "  %-50s %d 行" % r


def fmt_py_functions(r):
    """超长 / 高复杂度函数条目的单行格式化。"""
    rel, name, lineno, span, cc = r
    return "  %-40s %-28s L%-5d 行数=%-5d cc=%d" % (rel, name, lineno, span, cc)


def fmt_duplicates(r):
    """重复代码块条目：一行里列出所有出现位置，避免多行输出打断报告格式。"""
    places = r[0]
    return "  出现 %d 处：%s" % (len(places), "  ".join("%s L%d" % (p[0], p[1]) for p in places))
