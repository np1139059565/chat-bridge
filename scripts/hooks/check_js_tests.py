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
    # node --test 自动发现目录下的 *.test.js
    proc = subprocess.run([node, "--test", test_dir], capture_output=True)
    out = (proc.stdout or b"").decode("utf-8", "replace")
    err = (proc.stderr or b"").decode("utf-8", "replace")
    if proc.returncode == 0:
        # 只回显汇总行，避免刷屏
        for line in (out + err).splitlines():
            if line.startswith(("# tests", "# pass", "# fail")):
                print(line)
        return 0
    # 失败：完整打印，便于定位
    print(out)
    print(err, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
