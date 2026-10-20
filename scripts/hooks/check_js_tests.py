#!/usr/bin/env python3
"""pre-commit 前端逻辑测试钩子

职责：运行 flask_server/tests/js/ 下的前端纯逻辑测试（node 自带测试运行器）。

为什么需要它：
    前端逻辑（失败分类、断开判定等）此前无任何回归安全网——
    浏览器行为测试跑不到，Python 测试也覆盖不了。抽出纯逻辑后，
    由本钩子在每次提交时自动验证，防止前端逻辑被改坏。

设计取舍：
    - node 缺失时「跳过」而非报错：钩子不应把环境缺失误判为代码错误
      （与 check_syntax.py 一致）。
    - 测试目录不存在时跳过：允许仓库在无前端测试时正常提交。

用法（由 pre-commit 调用）：
    python scripts/hooks/check_js_tests.py

退出码：0 = 全部通过或跳过；1 = 存在失败的测试。
"""
import glob
import os
import shutil
import subprocess
import sys


def _find_node():
    """查找可用的 node 可执行文件。

    顺序：环境变量 NODE_BIN → PATH → 本地便携安装目录。
    与 check_syntax.py 口径一致，允许 node 便携版放 D:\\mydata\\tools 下。
    """
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


def _repo_root():
    """本脚本位于 scripts/hooks/ 下，向上两级为仓库根。"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    """入口：找到 node 与前端测试目录，运行测试；无 node 或无测试则跳过。"""
    node = _find_node()
    if not node:
        print("跳过前端测试：未找到 node")
        return 0
    test_dir = os.path.join(_repo_root(), "flask_server", "tests", "js")
    if not os.path.isdir(test_dir):
        print("跳过前端测试：无 %s" % test_dir)
        return 0
    # 先展开出具体测试文件：新版 node 会把目录参数当作模块路径解析，
    # 直接传目录会报 MODULE_NOT_FOUND，因此改为传文件列表。
    test_files = sorted(glob.glob(os.path.join(test_dir, "*.test.js")))
    if not test_files:
        print("跳过前端测试：%s 下无 *.test.js" % test_dir)
        return 0
    # node --test 接收具体文件路径，逐个发现并运行；
    # 同时打开内置覆盖率，供下方阈值检查使用（无需任何第三方依赖）。
    proc = subprocess.run(
        [node, "--test", "--experimental-test-coverage"] + test_files,
        capture_output=True)
    out = (proc.stdout or b"").decode("utf-8", "replace")
    err = (proc.stderr or b"").decode("utf-8", "replace")
    if proc.returncode != 0:
        # 失败：完整打印，便于定位
        print(out)
        print(err, file=sys.stderr)
        return 1
    # 只回显汇总行，避免刷屏。
    # node 新版汇总行以「ℹ 」开头，旧版以「# 」开头，两种都识别。
    for line in (out + err).splitlines():
        stripped = line.strip()
        if stripped.startswith(("# tests", "# pass", "# fail",
                                "ℹ tests", "ℹ pass", "ℹ fail")):
            print(stripped)
    # 覆盖率门禁：低于阈值即判失败，防止覆盖率悄悄退化
    return _check_coverage(out + err)


def _parse_coverage(report):
    """从覆盖率报告里解析出各源文件的行覆盖率与分支覆盖率。

    报告形如：
        # ..\\extend\\lib\\dom-utils.js | 82.67 | 75.00 | 90.00 | 114-139
    测试文件自身的行不计入（它们不是被测对象）。
    @param report 完整的命令输出
    @returns [(文件名, 行覆盖率, 分支覆盖率)]
    """
    rows = []
    in_report = False
    for line in report.splitlines():
        stripped = line.strip()
        # 只在报告区间内解析，避免误读测试输出里的其它表格
        if "start of coverage report" in stripped:
            in_report = True
            continue
        if "end of coverage report" in stripped:
            break
        if not in_report or not stripped.startswith("#"):
            continue
        parts = [p.strip() for p in stripped.lstrip("#").split("|")]
        # 表头与分隔线、汇总行的格式都不符，按列数与首列内容排除
        if len(parts) < 4:
            continue
        name = parts[0]
        if not name.endswith(".js"):
            continue
        # 测试文件本身不是被测对象，不计入门禁
        if "tests" + os.sep + "js" in name or "tests/js" in name:
            continue
        try:
            line_pct = float(parts[1])
            branch_pct = float(parts[2])
        except ValueError:
            continue
        rows.append((name, line_pct, branch_pct))
    return rows


# 覆盖率阈值：按当前实测值留出余量，既能拦住退化、又不会因小幅波动误报。
MIN_LINE_PCT = 90.0
MIN_BRANCH_PCT = 70.0


def _check_coverage(report):
    """检查各被测源文件的行覆盖率与分支覆盖率是否达到阈值。

    只约束「已被测试覆盖到的文件」：未被任何测试加载的文件不在报告里，
    本门禁不对其做要求（那属于补测试的范围，不是防退化）。
    @param report 完整的命令输出
    @returns 0 达标；1 有文件低于阈值
    """
    rows = _parse_coverage(report)
    if not rows:
        # 拿不到覆盖率数据（版本不支持等）：跳过而非误判失败
        print("跳过覆盖率门禁：未解析到覆盖率报告")
        return 0
    failed = []
    for name, line_pct, branch_pct in rows:
        if line_pct < MIN_LINE_PCT:
            failed.append("%s 行覆盖率 %.2f%% < %.0f%%" % (name, line_pct, MIN_LINE_PCT))
        if branch_pct < MIN_BRANCH_PCT:
            failed.append("%s 分支覆盖率 %.2f%% < %.0f%%" % (name, branch_pct, MIN_BRANCH_PCT))
    if failed:
        print("覆盖率未达标：")
        for f in failed:
            print("  " + f)
        return 1
    print("覆盖率达标：%d 个源文件（行 ≥%.0f%%、分支 ≥%.0f%%）"
          % (len(rows), MIN_LINE_PCT, MIN_BRANCH_PCT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
