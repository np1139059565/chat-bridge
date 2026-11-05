"""pre-commit 钩子的公共能力

为什么需要：多个钩子脚本都要「找 node 可执行文件」，此前各复制一份实现，
任一处调整都要改多遍，漏改会让不同钩子对「有没有 node」判断不一致——
表现为一个钩子跑、另一个跳过。集中到此处后口径只有一份。

与本文件的兄弟模块关系：各钩子脚本直接导入本模块；因它们被 pre-commit
以脚本方式直接执行，所在目录自动在导入路径上，无需额外调整 sys.path。

与 scripts/qcommon.py 的区别：那是质量检查脚本（check_quality / quality_rules）
的公共层，服务于「扫描全工程」；本模块服务于「提交前钩子」，两者职责不同，
故不合并。
"""
import glob
import os
import shutil


def find_node():
    """查找可用的 node 可执行文件。

    顺序：环境变量 NODE_BIN → PATH → 本地便携安装目录。
    本工程允许把 node 便携版解压到 D:\\mydata\\tools 下而不进系统 PATH，
    故补充目录探测，避免「装了 node 却仍被跳过」。

    @returns node 可执行文件路径；找不到返回 None
    """
    # 优先用显式指定的路径：便于在同一台机器上切换 node 版本
    env = os.environ.get("NODE_BIN")
    if env and os.path.isfile(env):
        return env
    # 其次走系统 PATH
    found = shutil.which("node")
    if found:
        return found
    # 最后探测本地便携安装目录：取版本号最大的那个
    candidates = []
    for base in (r"D:\mydata\tools", os.path.join(os.path.expanduser("~"), "nodejs")):
        candidates += glob.glob(os.path.join(base, "node-*", "node.exe"))
    return sorted(candidates)[-1] if candidates else None
