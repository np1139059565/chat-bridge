"""工程质量检查 —— 公共基础函数

多个检查脚本（check_quality / quality_rules）共用同一套基础能力，集中在此，
避免各脚本各自复制一份导致口径漂移，也避免被「重复代码」检测误判。

提供：
  - 常量：跳过目录、源码扩展名、重复检测扩展名
  - iter_files(root, exts)：遍历工程内源码文件
  - read_lines(path)：读取文件全部行
  - is_comment_or_blank(line)：空行 / 纯注释行判定
  - cyclomatic(node)：Python AST 节点圈复杂度
"""
import ast
import os

# 扫描时跳过的目录：第三方依赖、构建产物、缓存
SKIP_DIRS = {"__pycache__", "node_modules", ".git", "dist", "build", "out", "coverage", "vendor"}
# 参与扫描的源码扩展名
SOURCE_EXTS = (".py", ".js", ".css", ".html")
# 参与「重复代码」检测的扩展名：只针对代码
DUP_EXTS = (".py", ".js")


def iter_files(root, exts=None):
    """遍历工程内源码文件，跳过 SKIP_DIRS。

    @param root 工程根目录
    @param exts 限定扩展名元组；缺省用 SOURCE_EXTS
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


# 豁免路径：第三方库 / 压缩产物不参与长行与函数检查
EXEMPT_PREFIXES = (
    "extend/lib/vue.global.prod.js",
    "skills/debug_chrome/extension/vendor/",
    "skills/debug_chrome/extension/shared/vendor/",
)


def is_exempt(rel):
    """判断相对路径是否属于豁免范围（第三方库 / 压缩产物）。"""
    norm = rel.replace("\\", "/")
    return any(norm.startswith(p) for p in EXEMPT_PREFIXES) or norm.endswith(".min.js")
