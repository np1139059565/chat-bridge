"""文档与代码一致性校验

目的：防止文档漂移——代码新增路由 / 工具后，接口文档未同步更新。
对比两处「代码事实」与文档记载，缺漏即报警，供提交钩子拦住。

校验项：
  1. 路由：routes/*.py 中 @bp.route 声明的路径，是否都在 docs/api-reference.md 中出现；
  2. 工具：tool_meta.TOOLS 的每个工具名，是否都在 docs/api-reference.md 中出现。

设计取舍：
- 只做「文档是否提及」的存在性校验，不校验描述内容是否准确（那需人工判断）；
- 允许在 DOC_EXEMPT 中登记显式豁免项（如纯页面、静态资源），避免误报。

用法：
    python scripts/check_doc_sync.py
退出码：0 = 全部一致；1 = 存在未收录项。
"""
import os
import re
import sys

# 工程根：本脚本位于 scripts/ 下，上一级即工程根
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 接口文档路径
API_DOC = os.path.join(ROOT, "docs", "api-reference.md")
# 路由源码目录
ROUTES_DIR = os.path.join(ROOT, "flask_server", "routes")
# 工具声明模块目录（core 在 sys.path 上，直接 import）
FLASK_DIR = os.path.join(ROOT, "flask_server")

# 显式豁免：这些路由不要求写进接口文档（纯页面 / 静态资源 / 健康检查等）
DOC_EXEMPT_PATHS = {
    "/",                      # 首页
    "/memory-graph",          # 图谱页面
    "/memory-graph-assets/<path:name>",  # 图谱页面静态资源
    "/memory_graph.html",     # 图谱页面别名
}


def collect_routes():
    """扫描 routes/*.py，收集所有 @bp.route 声明的路径。"""
    out = set()
    if not os.path.isdir(ROUTES_DIR):
        return out
    for fn in sorted(os.listdir(ROUTES_DIR)):
        if not fn.endswith(".py"):
            continue
        p = os.path.join(ROUTES_DIR, fn)
        try:
            text = open(p, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for m in re.finditer(r'@bp\.route\(\s*"([^"]+)"', text):
            out.add(m.group(1))
    return out


def collect_tools():
    """导入 tool_meta，取出内置工具名集合。"""
    sys.path.insert(0, FLASK_DIR)
    try:
        import paths  # noqa: F401  确保 core 加入搜索路径
        import tool_meta
        return set(tool_meta.TOOLS.keys())
    except Exception as e:
        print("[doc-sync] 无法导入 tool_meta：%s（跳过工具校验）" % e)
        return set()


def read_doc():
    """读取接口文档全文并规范化；不存在返回空串。

    规范化：把文档里常见的 HTML 转义还原（&lt; → <，&gt; → >），
    并把多余空白折叠，便于与代码中的路由路径做子串匹配。
    """
    try:
        text = open(API_DOC, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return ""
    # 还原 HTML 转义：文档中 <skill> 常被写成 &lt;skill&gt;
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    return text


def normalize_route(path):
    """把路由路径里的参数占位归一化，便于跨写法比对。

    例：/api/cards/<card_id> 与文档中的 /api/cards/<id> 视为同一路由；
    /memory/node/<int:node_id> 归一化为 /memory/node/<param>。
    做法：把所有 <...> 段替换为固定占位 <param>。
    """
    return re.sub(r'<[^>]*>', '<param>', path)


def _report_missing(label, missing):
    """打印一类缺漏清单；无缺漏返回 0，否则返回条数。

    @param label   缺漏类别描述（如「路由」）
    @param missing 缺失项列表
    @returns 缺漏条数
    """
    if not missing:
        return 0
    print("以下%s未收录进接口文档（%d 项）：" % (label, len(missing)))
    for m in missing:
        print("  ", m)
    return len(missing)


def _check_routes(doc_norm):
    """校验路由是否都已收录；返回缺漏路由数。

    @param doc_norm 归一化后的文档全文
    @returns 缺漏条数
    """
    missing = []
    for r in sorted(collect_routes()):
        if r in DOC_EXEMPT_PATHS:
            continue
        if normalize_route(r) not in doc_norm:
            missing.append(r)
    return _report_missing("路由", missing)


def _check_tools(doc):
    """校验工具名是否都已收录；返回缺漏工具数。

    @param doc 文档全文（原文，工具名不需归一化）
    @returns 缺漏个数
    """
    missing = [t for t in sorted(collect_tools()) if t not in doc]
    return _report_missing("工具", missing)


# 文档目录：本项校验覆盖 docs 下全部 Markdown，而非仅接口文档
DOCS_DIR = os.path.join(ROOT, "docs")
# 被引用路径的识别模式：反引号包裹、含目录分隔符、带具体扩展名
# 只匹配形如 a/b/c.py 的具体路径；含 * 或 < > 的模式串（通配 / 占位）不参与校验
PATH_REF_PATTERN = re.compile(r"`([A-Za-z0-9_\-./]+\.(?:py|js|md|yaml|json|css|html))`")

# 历史记录类文档：记录的是当时的文件状态与改动过程，其中的旧路径属史实，
# 不随代码演进同步，故不参与「引用文件是否存在」校验。
HISTORY_DOCS = (
    "refactor-plan.md",      # 重构执行计划与批次记录
    "code-review-report.md", # 走查当时的结论快照
)


def _is_valid_ref(ref):
    """判断一条引用是否值得做存在性校验。

    排除三类：通配 / 占位写法（含 * < > ?）、无目录分隔符的纯文件名
    （同名文件太多，无法唯一定位）、文档中的演示用假路径。

    @param ref 从文档中提取到的路径字符串
    @returns 需要校验时返回 True
    """
    if "*" in ref or "<" in ref or "?" in ref:
        return False
    if "/" not in ref:
        return False
    # 运行时产物不参与存在性校验：data/ 下的文件由服务运行期间生成，
    # 文档引用它们是为了说明「会生成什么」，静态检查必然误报缺漏。
    if ref.startswith(RUNTIME_DATA_PREFIXES):
        return False
    return not any(pat in ref for pat in REF_SKIP_PATTERNS)


def _scan_doc_refs(path, out):
    """扫描单个文档，把其中有效的引用路径追加到 out。

    @param path 文档路径
    @param out  收集结果集合（原地追加）
    """
    try:
        text = open(path, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return
    for m in PATH_REF_PATTERN.finditer(text):
        ref = m.group(1)
        if _is_valid_ref(ref):
            out.add(ref)


def collect_path_refs():
    """扫描 docs 下全部 Markdown，收集其中以反引号包裹的具体文件路径。

    只收含目录分隔符的路径（如 flask_server/core/memory_db.py），
    纯文件名（如 definition.yaml）存在多处同名可能，无法唯一定位，故跳过。
    历史记录类文档记录当时状态，其中的旧路径属史实，不参与校验。

    @returns 路径字符串集合（原样，未归一化）
    """
    out = set()
    if not os.path.isdir(DOCS_DIR):
        return out
    for fn in sorted(os.listdir(DOCS_DIR)):
        if not fn.endswith(".md") or fn in HISTORY_DOCS:
            continue
        _scan_doc_refs(os.path.join(DOCS_DIR, fn), out)
    return out


# 引用路径的解析基准：文档中既有工程根相对路径，也有模块内相对路径，
# 逐个基准尝试，任一命中即视为有效，避免把相对写法误报为缺漏。
REF_BASES = (
    "",                      # 工程根
    "flask_server",          # 服务端模块内相对
    "flask_server/routes",   # 路由文件常以同目录名引用
    "extend",                # 插件内相对
    "extend/content",
    "extend/dialog",
    "extend/dialog/parts",
    "extend/dialog/styles",
    "extend/lib",
    "skills",
    # 调试扩展自身的文档以其扩展根为基准书写
    "skills/debug_chrome/extension",
    "skills/debug_chrome/extension/content",
    "skills/debug_chrome/extension/shared",
    "skills/debug_chrome/extension/drawer",
)

# 运行时产物前缀：这些路径由服务运行期间生成，文档引用它们是说明「会产出什么」，
# 静态检查时文件可能尚未存在，故一律跳过存在性校验。
RUNTIME_DATA_PREFIXES = (
    "data/",
    "flask_server/data/",
)

# 示例占位：文档中用于演示的假路径，并非真实文件引用，不参与校验
REF_SKIP_PATTERNS = (
    "xxx/",      # 如 skills/xxx/SKILL.md 这类演示用占位
    "example/",
    "示例/",
)


def _check_path_refs():
    """校验文档中引用的文件路径是否真实存在；返回缺漏条数。

    目的：文档里写到的模块被删除或改名后，此处立即报警，
    避免文档长期引用不存在的文件却无人察觉。

    解析策略：对每个引用依次套用 REF_BASES 中的基准，任一命中即通过；
    全部基准都不命中才算缺漏。这样可容纳文档里「模块内相对」的写法，
    同时仍能发现「文件已被移走、文档还写着旧位置」这类真实漂移。

    @returns 缺漏条数
    """
    missing = []
    for ref in sorted(collect_path_refs()):
        rel = ref.replace("/", os.sep)
        # 逐个基准尝试解析，命中即跳出
        found = False
        for base in REF_BASES:
            target = os.path.join(ROOT, base, rel) if base else os.path.join(ROOT, rel)
            # 归一化 .. 片段后再判断，兼容 ../lib/dom-utils.js 这类写法
            if os.path.exists(os.path.normpath(target)):
                found = True
                break
        if not found:
            missing.append(ref)
    return _report_missing("文档引用的文件", missing)


def main():
    """执行路由、工具与文档引用路径的收录校验。"""
    doc = read_doc()
    if not doc:
        print("接口文档不存在或为空：%s" % API_DOC)
        return 1
    # 文档做参数占位归一化，消除 <id> / <card_id> 之类的写法差异
    problems = _check_routes(normalize_route(doc)) + _check_tools(doc) + _check_path_refs()
    if problems:
        print("\n文档同步校验未通过：共 %d 项缺漏。" % problems)
        return 1
    print("文档同步校验通过：路由、工具与文档引用路径均一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
