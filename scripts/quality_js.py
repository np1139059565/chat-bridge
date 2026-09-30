"""工程质量检查 —— JS 函数体行数检查（从 quality_rules.py 抽出）

现有检查只对 Python 做 AST 分析，JS 是盲区。本模块用启发式扫描估算 JS
函数体行数，超阈值即报。

扫描思路：
  1. 先剥离字符串与注释，只留结构字符（否则字符串里的花括号会打乱大括号配平）；
  2. 逐行匹配函数起始（function 声明 / 赋值 function / 赋值箭头函数）；
  3. 从起始行按大括号配平找到函数结束，得出行数；
  4. 数据工厂（纯 return 对象）与装配工厂（createXxx）豁免——行数来自字段多，
     不是逻辑复杂；第三方库 / 压缩产物整体豁免。

启发式扫描，不追求 100% 精确，目的是给超长函数一个信号。
"""
import os
import re

import qcommon

# JS 函数体行数上限（粗略扫描）
JS_FUNC_LINE_LIMIT = 80

# JS 函数起始行的三种形态：function 声明、赋值 function、赋值箭头函数
_PAT_FUNC = re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(")
_PAT_FN = re.compile(r"([A-Za-z_$][\w$.]*)\s*=\s*(?:async\s+)?function\b")
_PAT_ARROW = re.compile(r"([A-Za-z_$][\w$.]*)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>")

# JS 字符串与注释：用于剥离后只留结构字符，避免字符串里的花括号打乱配平
_JS_TOKENS = re.compile(
    r"/\*.*?\*/"                    # 块注释
    r"|//[^\n]*"                     # 行注释
    r"|\"(?:\\.|[^\"\\])*\""          # 双引号字符串
    r"|'(?:\\.|[^'\\])*'"            # 单引号字符串
    r"|`(?:\\.|[^`\\])*`",           # 模板字符串
    re.DOTALL)


def _strip_js_lines(lines):
    """剥离 JS 字符串与注释，只留结构字符（按行返回，行数与输入一致）。

    用正则一次匹配所有字符串 / 注释，替换为空或占位符，并把匹配内容里的换行
    原样补回，保证行号不漂移。这样字符串里的花括号就不会干扰大括号配平。
    """
    text = "\n".join(lines)

    def _repl(m):
        s = m.group(0)
        filler = "" if s.startswith(("/*", "//")) else "''"
        return filler + "\n" * s.count("\n")

    return _JS_TOKENS.sub(_repl, text).split("\n")


def _match_fn_name(line):
    """从一行里匹配 JS 函数名；不是函数起始行返回空串。"""
    m = _PAT_FUNC.search(line) or _PAT_FN.search(line) or _PAT_ARROW.search(line)
    return m.group(1) if m else ""


def _find_block_end(code, start):
    """从 start 行起按大括号配平，返回函数结束行号；未出现左括号返回 -1。"""
    depth = 0
    started = False
    for j in range(start, len(code)):
        seg = code[j]
        depth += seg.count("{") - seg.count("}")
        if "{" in seg:
            started = True
        if started and depth <= 0:
            return j
    return -1


def _js_functions(lines):
    """粗略扫描 JS 函数：返回 [(起始行, 名字, 行数)]。启发式，不追求精确。"""
    code = _strip_js_lines(lines)
    results = []
    for i, line in enumerate(code):
        name = _match_fn_name(line)
        if not name:
            continue
        end = _find_block_end(code, i)
        if end >= 0:
            results.append((i + 1, name, end - i + 1))
    return results


def _is_data_factory(code, start, end):
    """判断函数体是否为「纯数据工厂」：整段基本只有一个 return 对象/数组字面量。

    这类函数（Vue 的 data 工厂、返回一组方法的工厂）行数来自字段多，
    不是逻辑复杂，拆它没有意义，故从「函数体行数」检查中豁免。
    判据：函数体内只有一个 return，且返回的是 { 或 [ 开头的字面量。
    """
    body = [code[k].strip() for k in range(start, end + 1)]
    returns = [l for l in body if l.startswith("return")]
    if len(returns) != 1:
        return False
    r = returns[0]
    return r.startswith("return {") or r.startswith("return [")


def check_js_functions(root):
    """检查：JS 函数体行数超过阈值（数据工厂 / 装配工厂 / 第三方库豁免）。"""
    out = []
    for p in qcommon.iter_files(root, (".js",)):
        rel = os.path.relpath(p, root)
        if qcommon.is_exempt(rel):
            continue
        raw = qcommon.read_lines(p)
        code = _strip_js_lines(raw)
        for lineno, name, span in _js_functions(raw):
            if span <= JS_FUNC_LINE_LIMIT:
                continue
            # 装配工厂（createXxx）豁免：行数来自「装的方法多」，不是逻辑复杂。
            if name.split('.')[-1].startswith('create'):
                continue
            # _js_functions 的 lineno 是 1 基，换算成 0 基的行号范围
            if _is_data_factory(code, lineno - 1, lineno - 1 + span - 1):
                continue
            out.append((rel, name, lineno, span))
    return out
