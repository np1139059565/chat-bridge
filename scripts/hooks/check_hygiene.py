#!/usr/bin/env python3
"""pre-commit 仓库卫生钩子

拦截两类「不该入库」的内容：
1. 临时备份 / 编辑器残留文件（*.bak、*~、*.orig、*.tmp、*.pyc 等）
2. 超大文件（默认阈值 450 行）——与本工程的文件拆分约定一致，
   防止刚拆分完又被新的巨型文件重新填满。

阈值说明：
- 行数阈值对源码（.py/.js/.css/.html）生效；
- 以下内容豁免：第三方库（vendor/）、锁文件、以及显式在
  EXEMPT_PATHS 中登记的文件（如生成物或数据文件）。

用法（由 pre-commit 调用）：
    python scripts/hooks/check_hygiene.py <文件1> <文件2> ...

退出码：0 = 通过；1 = 存在违规项（详情打印到 stderr）。
"""
import os
import sys

# 行数阈值：与本工程 docs/refactor-plan.md 的验收标准保持一致
LINE_LIMIT = 450

# 需要做行数检查的源码扩展名
SOURCE_EXTS = (".py", ".js", ".css", ".html")

# 临时 / 备份文件的文件名特征
BAD_NAME_PATTERNS = (".bak", ".orig", ".tmp", ".rej", ".pyc", ".pyo")

# 豁免行数检查的路径前缀（第三方库、构建产物）
EXEMPT_PREFIXES = (
    "skills/debug_chrome/extension/vendor/",
    "extend/lib/vue.global.prod.js",
    "skills/debug_chrome/extension/shared/vendor/",
)


def is_bad_name(path):
    """判断文件名是否为临时/备份残留。"""
    name = os.path.basename(path)
    if name.endswith("~"):
        return True
    return any(name.endswith(p) for p in BAD_NAME_PATTERNS)


def is_exempt(path):
    """判断路径是否豁免行数检查（第三方库、压缩产物等）。"""
    norm = path.replace("\\", "/")
    return any(norm.startswith(p) for p in EXEMPT_PREFIXES) or norm.endswith(".min.js")


def count_lines(path):
    """统计文件行数；读取失败返回 -1（视为跳过）。"""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return sum(1 for _ in fh)
    except Exception:
        return -1


def main(argv):
    """入口：检查文件卫生与行数，收集全部违规项后统一输出。"""
    bad_names = []
    too_long = []
    for path in argv:
        if not os.path.isfile(path):
            continue
        # 1) 临时 / 备份文件：一律拦截
        if is_bad_name(path):
            bad_names.append(path)
            continue
        # 2) 超大文件：仅对源码、且非豁免路径生效
        if not path.lower().endswith(SOURCE_EXTS) or is_exempt(path):
            continue
        n = count_lines(path)
        if n > LINE_LIMIT:
            too_long.append((path, n))

    if not bad_names and not too_long:
        return 0
    for p in bad_names:
        print("[临时/备份文件] %s" % p, file=sys.stderr)
    for p, n in too_long:
        print("[超大文件] %s（%d 行，上限 %d 行）" % (p, n, LINE_LIMIT), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
