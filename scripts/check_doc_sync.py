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


def main():
    """执行路由与工具的文档收录校验。"""
    doc = read_doc()
    if not doc:
        print("接口文档不存在或为空：%s" % API_DOC)
        return 1
    # 文档做参数占位归一化，消除 <id> / <card_id> 之类的写法差异
    problems = _check_routes(normalize_route(doc)) + _check_tools(doc)
    if problems:
        print("\n文档同步校验未通过：共 %d 项缺漏。" % problems)
        return 1
    print("文档同步校验通过：路由与工具均已收录。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
