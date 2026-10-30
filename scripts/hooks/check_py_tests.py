#!/usr/bin/env python3
"""pre-commit 后端单元测试钩子

职责：运行 flask_server/tests/ 下的 Python 单元测试（unittest 或 pytest）。

为什么需要它：
    本工程原有七个钩子全是静态检查（语法、行数、参数个数、注释率等），
    没有任何一个执行测试代码。结果是一次返回值解包错误让语音合成
    100% 失败，而所有钩子全绿、13 个语音测试也全绿——因为那些测试
    从未被提交闸门触发过。静态检查看不出「返回值个数不匹配」这类
    语义错误，只有真的跑一遍才能发现。

设计取舍：
    - 优先用 pytest（若可用），否则降级 unittest：两者都在本机时可自由选择，
      缺失任一个不影响提交。
    - 两个都缺失时「跳过」而非报错：与 check_js_tests.py 口径一致，
      不把环境缺失误判为代码错误。
    - pytest 分支同时校验覆盖率下限（fail_under 写在 flask_server/.coveragerc）。
      只跑测试不看覆盖率，会出现「全绿但大段代码从未执行」的情况；
      装了 pytest-cov 才校验，没装则只跑测试。
    - 只跑 flask_server/tests 下的用例，不递归进 js 子目录
      （前端测试由 check_js_tests.py 负责）。
    - 超时保护：整套测试预计 1-2 分钟，超过 300 秒视为异常并中止，
      避免钩子卡死阻塞提交。

用法（由 pre-commit 调用）：
    python scripts/hooks/check_py_tests.py

退出码：0 = 全部通过或跳过；1 = 存在失败的测试或执行异常。
"""
import os
import subprocess
import sys

# 整套测试的耗时上限（秒）：超过即中止，防止钩子无限等待
TEST_TIMEOUT = 300


def _repo_root():
    """本脚本位于 scripts/hooks/ 下，向上两级为仓库根。"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _has_module(name):
    """判断当前解释器能否导入指定模块。

    @param name 模块名（如 pytest）
    @returns 可导入返回 True
    """
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _run_pytest(server_dir):
    """用 pytest 运行后端测试，并在可用时校验覆盖率下限。

    覆盖率下限写在 flask_server/.coveragerc 的 fail_under，
    由 --cov 读取，低于下限时 pytest 返回非零，提交被拦住。
    没有装 pytest-cov 时只跑测试、不校验覆盖率，
    避免把「本机没装插件」误判成「代码不达标」。

    @param server_dir flask_server 目录
    @returns (returncode, 输出文本)
    """
    args = [sys.executable, "-m", "pytest", "tests", "-q", "--ignore=tests/js"]
    if _has_module("pytest_cov"):
        # --cov 不传路径即按 .coveragerc 的 source 统计，口径集中在一处维护
        args += ["--cov", "--cov-report=term"]
    proc = subprocess.run(
        args, cwd=server_dir, capture_output=True, timeout=TEST_TIMEOUT,
    )
    out = (proc.stdout or b"").decode("utf-8", "replace")
    err = (proc.stderr or b"").decode("utf-8", "replace")
    return proc.returncode, out + err


def _run_unittest(server_dir):
    """用 unittest 运行后端测试（自动发现 tests 包下的用例）。

    @param server_dir flask_server 目录
    @returns (returncode, 输出文本)
    """
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"],
        cwd=server_dir, capture_output=True, timeout=TEST_TIMEOUT,
    )
    out = (proc.stdout or b"").decode("utf-8", "replace")
    err = (proc.stderr or b"").decode("utf-8", "replace")
    return proc.returncode, out + err


def main():
    """入口：选择可用的测试运行器，执行后端测试并汇报结果。"""
    server_dir = os.path.join(_repo_root(), "flask_server")
    test_dir = os.path.join(server_dir, "tests")
    if not os.path.isdir(test_dir):
        print("跳过后端测试：无 %s" % test_dir)
        return 0

    # 优先 pytest：输出更简洁，失败定位更清楚
    if _has_module("pytest"):
        runner = "pytest"
    elif _has_module("unittest"):
        runner = "unittest"
    else:
        print("跳过后端测试：未找到 pytest 或 unittest")
        return 0

    try:
        if runner == "pytest":
            code, output = _run_pytest(server_dir)
        else:
            code, output = _run_unittest(server_dir)
    except subprocess.TimeoutExpired:
        print("后端测试超时（%d 秒），已中止" % TEST_TIMEOUT)
        return 1
    except Exception as e:
        print("后端测试执行异常：%s" % e)
        return 1

    if code == 0:
        # 只回显最后几行汇总，避免每次提交刷屏
        tail = [l for l in output.splitlines() if l.strip()][-3:]
        for line in tail:
            print(line)
        return 0

    # 失败：完整回显，便于定位
    print(output)
    return 1


if __name__ == "__main__":
    sys.exit(main())
