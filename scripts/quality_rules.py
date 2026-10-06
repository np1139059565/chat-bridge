"""工程质量检查 —— 九项扩展规则

在 check_quality.py 的三项基础检查（文件行数 / 函数行数与圈复杂度 / 重复块）
之外，补充更细的结构约束，全部面向「可维护性」：

  1. 函数参数个数上限   —— 参数越多，调用越易错、职责越杂
  2. 嵌套深度上限       —— 深层嵌套是理解成本的主要来源
  3. 单行长度上限       —— 过长行破坏可读性与并排 diff
  4. 文件级圈复杂度     —— 单函数之外，整文件的逻辑总量
  5. 函数个数上限       —— 一个文件函数过多 = 职责过载
  6. JS 函数级检查      —— 现有检查只覆盖 Python，JS 是盲区
  7. 注释率下限         —— 呼应「文件/函数加注释」的规范
  8. 循环导入检测       —— A 引 B、B 引 A 会埋下初始化顺序 bug
  9. 命名规范           —— Python 函数 snake_case / 类 PascalCase

每个 check_xxx 返回违规列表；report(root) 打印报告；main(argv) 供钩子调用。
"""
import ast
import os
import re
import sys

import qcommon
# JS 函数体检查已抽到独立模块 quality_js（避免本文件超行数上限）
from quality_js import check_js_functions, JS_FUNC_LINE_LIMIT

# ---------- 各检查项的阈值（集中于此，便于统一调参） ----------
PARAM_LIMIT = 6        # 函数参数个数上限
NEST_LIMIT = 4         # 嵌套深度上限（if/for/while/with/try 层级）
LINE_LEN_LIMIT = 140   # 单行字符数上限
FILE_CC_LIMIT = 120    # 单文件圈复杂度总和上限
FUNC_COUNT_LIMIT = 35  # 单文件函数个数上限（小函数成组是正常结构，阈值放宽）
COMMENT_RATIO_MIN = 0.06  # 注释率下限（注释行 / 总行）

# 命名规范：Python 函数必须 snake_case；类必须 PascalCase
PY_FUNC_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
PY_CLASS_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")


def _py_parse(path):
    """解析 Python 文件为 AST；失败返回 None。"""
    try:
        return ast.parse("\n".join(qcommon.read_lines(path)))
    except SyntaxError:
        return None


# ---------- 检查 1：函数参数个数 ----------
def _param_count(node):
    """统计函数显式参数个数（不含 self / cls）。"""
    cnt = len(node.args.args) + len(node.args.kwonlyargs)
    if node.args.args and node.args.args[0].arg in ("self", "cls"):
        cnt -= 1
    return cnt


def check_params(root):
    """检查 1：函数参数个数超过阈值。"""
    out = []
    for p in qcommon.iter_files(root, (".py",)):
        tree = _py_parse(p)
        if tree is None:
            continue
        rel = os.path.relpath(p, root)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cnt = _param_count(node)
                if cnt > PARAM_LIMIT:
                    out.append((rel, node.name, node.lineno, cnt))
    return out


# ---------- 检查 2：嵌套深度 ----------
def _nest_depth(node, depth=0):
    """递归求某节点子树的最大嵌套深度。

    elif 链在 AST 里表现为 orelse 中嵌套的 If，并非真实缩进加深，
    故对「If 的 orelse 里的 If」不加深度，避免把 if/elif 误报为深嵌套。
    """
    block_types = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)
    best = depth
    for ch in ast.iter_child_nodes(node):
        is_elif = isinstance(ch, ast.If) and isinstance(node, ast.If) and any(ch is o for o in node.orelse)
        if is_elif:
            best = max(best, _nest_depth(ch, depth))
        elif isinstance(ch, block_types):
            best = max(best, _nest_depth(ch, depth + 1))
        else:
            best = max(best, _nest_depth(ch, depth))
    return best


def check_nesting(root):
    """检查 2：函数体嵌套深度超过阈值。"""
    out = []
    for p in qcommon.iter_files(root, (".py",)):
        tree = _py_parse(p)
        if tree is None:
            continue
        rel = os.path.relpath(p, root)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                d = _nest_depth(node)
                if d > NEST_LIMIT:
                    out.append((rel, node.name, node.lineno, d))
    return out


# ---------- 检查 3：单行长度 ----------
# 字符串字面量：单行长度检查时先剥离，避免把「长文本」误判为「长代码行」
_STR_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`')


def _code_len(line):
    """返回一行剥离所有字符串字面量后的长度（近似「纯代码」长度）。"""
    return len(_STR_RE.sub("", line))


def check_line_length(root):
    """检查 3：单行字符数超过阈值（第三方库 / 压缩产物 / 长字符串豁免）。

    只对「纯代码部分」超长报警：提示词模板、注入脚本串这类长字符串是数据，
    强行换行反而损害可读性，故剥离字符串后再比对阈值。
    """
    out = []
    for p in qcommon.iter_files(root):
        rel = os.path.relpath(p, root)
        if qcommon.is_exempt(rel):
            continue
        for i, line in enumerate(qcommon.read_lines(p), 1):
            if len(line) <= LINE_LEN_LIMIT:
                continue
            # 排除含长 URL 的行：那是链接，不是代码结构问题
            if "http" in line:
                continue
            if _code_len(line) > LINE_LEN_LIMIT:
                out.append((rel, i, _code_len(line)))
    return out


# ---------- 检查 4：文件级圈复杂度 ----------
def _file_cc(tree):
    """累加一个文件内所有函数的圈复杂度（每个函数减 1，去掉其自身基数）。"""
    total = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            total += qcommon.cyclomatic(node) - 1
    return total


def check_file_cc(root):
    """检查 4：单文件圈复杂度总和超过阈值。"""
    out = []
    for p in qcommon.iter_files(root, (".py",)):
        tree = _py_parse(p)
        if tree is None:
            continue
        total = _file_cc(tree)
        if total > FILE_CC_LIMIT:
            out.append((os.path.relpath(p, root), total))
    return out


# ---------- 检查 5：函数个数 ----------
def check_func_count(root):
    """检查 5：单文件函数个数超过阈值。

    豁免 _h_ 前缀的指令处理函数：命令处理器天然成组（每条内置指令一个
    _h_xxx），属表驱动的正常形态，不应算作「职责过载」。
    """
    out = []
    for p in qcommon.iter_files(root, (".py",)):
        tree = _py_parse(p)
        if tree is None:
            continue
        cnt = sum(1 for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and not n.name.startswith("_h_"))
        if cnt > FUNC_COUNT_LIMIT:
            out.append((os.path.relpath(p, root), cnt))
    return out


# ---------- 检查 7：注释率 ----------
def _docstring_span(node):
    """返回节点首条 docstring 占用的行数；无 docstring 返回 0。"""
    body = getattr(node, "body", None) or []
    if not body:
        return 0
    first = body[0]
    ok = (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
          and isinstance(first.value.value, str))
    if not ok:
        return 0
    return (first.end_lineno or first.lineno) - first.lineno + 1


def _docstring_lines(path):
    """统计 Python 文件里 docstring 占用的行数（docstring 是字符串，非 # 注释）。"""
    tree = _py_parse(path)
    if tree is None:
        return 0
    owners = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    total = 0
    for node in ast.walk(tree):
        if isinstance(node, owners):
            total += _docstring_span(node)
    return total


def check_comment_ratio(root):
    """检查 7：注释率低于阈值（注释行 / 总行，含 Python docstring）。"""
    out = []
    for p in qcommon.iter_files(root, (".py", ".js")):
        lines = qcommon.read_lines(p)
        if len(lines) < 30:
            continue  # 太短的文件注释率无参考意义
        comments = sum(1 for l in lines if qcommon.is_comment_or_blank(l) and l.strip())
        if p.endswith(".py"):
            comments += _docstring_lines(p)
        ratio = comments / len(lines)
        if ratio < COMMENT_RATIO_MIN:
            out.append((os.path.relpath(p, root), round(ratio, 3)))
    return out


# ---------- 检查 8：循环导入 ----------
def _module_of(path, root):
    """由文件路径推出模块名（相对根、去扩展名、点号连接）。"""
    rel = os.path.relpath(path, root).replace("\\", "/")
    if rel.endswith(".py"):
        rel = rel[:-3]
    return rel.replace("/", ".")


def _imports_of(tree):
    """提取一个 Python 模块的导入目标模块名列表（绝对名）。"""
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.append(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _build_dep_graph(pkg, root):
    """建 flask_server 内部依赖图：模块名 → 它导入的本包模块集合。"""
    mod_files = {}
    for p in qcommon.iter_files(pkg, (".py",)):
        mod_files[_module_of(p, root)] = p
    graph = {}
    for mod, path in mod_files.items():
        tree = _py_parse(path)
        if tree is None:
            continue
        deps = set()
        for imp in _imports_of(tree):
            if imp.startswith("flask_server.") or imp in mod_files:
                deps.add(imp)
        graph[mod] = deps
    return graph


def _walk_cycles(node, graph, stack, visited, cycles):
    """深度优先遍历，发现回边则把 (起点, 终点) 记入 cycles。"""
    visited.add(node)
    stack.append(node)
    for nb in graph.get(node, ()):
        if nb in stack:
            cycles.append((node, nb))
        elif nb not in visited:
            _walk_cycles(nb, graph, stack, visited, cycles)
    stack.pop()


def check_import_cycles(root):
    """检查 8：flask_server 包内部的循环导入。"""
    pkg = os.path.join(root, "flask_server")
    if not os.path.isdir(pkg):
        return []
    graph = _build_dep_graph(pkg, root)
    cycles = []
    visited = set()
    for mod in graph:
        if mod not in visited:
            _walk_cycles(mod, graph, [], visited, cycles)
    return cycles


# ---------- 检查 9：命名规范 ----------
def _naming_issue(node):
    """返回 (类别, 名字) 若命名不规范，否则 None。"""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name.startswith("__") and node.name.endswith("__"):
            return None  # 魔术方法豁免
        return None if PY_FUNC_RE.match(node.name) else ("函数", node.name)
    if isinstance(node, ast.ClassDef):
        return None if PY_CLASS_RE.match(node.name) else ("类", node.name)
    return None


# 命名检查豁免的目录前缀（相对工程根，正斜杠）。
# 测试目录整体豁免：unittest 的用例类与生命周期钩子（setUp / tearDown /
# setUpClass 等）是框架约定名，不适用 snake_case / PascalCase 规则。
NAMING_EXEMPT_PREFIXES = ("flask_server/tests/",)


def check_py_naming(root):
    """检查 9：Python 命名规范（函数 snake_case、类 PascalCase）。

    测试目录（flask_server/tests/）整体豁免：其用例类与框架钩子遵循
    unittest 约定，不适用本规则。
    """
    out = []
    for p in qcommon.iter_files(root, (".py",)):
        rel = os.path.relpath(p, root)
        norm = rel.replace("\\", "/")
        # 测试目录整体跳过命名检查
        if any(norm.startswith(pref) for pref in NAMING_EXEMPT_PREFIXES):
            continue
        tree = _py_parse(p)
        if tree is None:
            continue
        for node in ast.walk(tree):
            issue = _naming_issue(node)
            if issue:
                out.append((rel, issue[0], issue[1], node.lineno))
    return out


# 检查项清单：名称 → (检查函数, 报告标题, 行格式化函数)
CHECKS = [
    ("params", check_params, "函数参数超过 %d 个" % PARAM_LIMIT, lambda r: "  %-46s %-24s L%-5d 参数=%d" % r),
    ("nesting", check_nesting, "嵌套深度超过 %d 层" % NEST_LIMIT, lambda r: "  %-46s %-24s L%-5d 深度=%d" % r),
    ("longline", check_line_length, "单行超过 %d 字符" % LINE_LEN_LIMIT, lambda r: "  %-46s L%-5d 长度=%d" % r),
    ("filecc", check_file_cc, "文件圈复杂度总和超过 %d" % FILE_CC_LIMIT, lambda r: "  %-46s cc=%d" % r),
    ("funccount", check_func_count, "函数个数超过 %d" % FUNC_COUNT_LIMIT, lambda r: "  %-46s 个数=%d" % r),
    ("jsfunc", check_js_functions, "JS 函数体超过 %d 行" % JS_FUNC_LINE_LIMIT, lambda r: "  %-46s %-24s L%-5d 行数=%d" % r),
    ("comment", check_comment_ratio, "注释率低于 %.0f%%" % (COMMENT_RATIO_MIN * 100), lambda r: "  %-46s 注释率=%.1f%%" % (r[0], r[1] * 100)),
    ("cycle", check_import_cycles, "循环导入", lambda r: "  %s <-> %s" % r),
    ("naming", check_py_naming, "命名不规范", lambda r: "  %-46s %s %s L%d" % r),
]


def run_all(root, keys=None):
    """执行全部（或指定）检查，返回 {检查名: 违规列表}。"""
    result = {}
    for key, fn, _title, _fmt in CHECKS:
        if keys and key not in keys:
            continue
        result[key] = fn(root)
    return result


def report(root, keys=None):
    """打印九项检查报告；存在任一违规返回 True。"""
    failed = False
    for key, fn, title, fmt in CHECKS:
        if keys and key not in keys:
            continue
        items = fn(root)
        print("=" * 70)
        print(title)
        if not items:
            print("  无")
            continue
        failed = True
        for it in items:
            print(fmt(it))
    return failed


def main(argv):
    """钩子入口：全量扫描工程，输出违规明细，有违规返回 1。

    传入文件仅用于定位工程根；结构类问题需看整体，单文件扫描会漏跨文件关系。
    """
    # __file__ = <root>/scripts/quality_rules.py，上两级即工程根
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    keys = [k for k, _f, _t, _x in CHECKS]
    failed = report(root, keys)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
