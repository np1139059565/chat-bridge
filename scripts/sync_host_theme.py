"""宿主主题探测 —— 共享真源同步脚本

背景：AI 工具调用镜像插件（extend）与 AI Style Debug Assistant
（skills/debug_chrome/extension）是两个独立的 Chrome 扩展，各自运行在隔离环境，
运行时无法共用同一文件。为消除「两份实现改一处忘一处」的风险，
采用「单一真源 + 同步生成副本」：

    真源：shared/host_theme.js
    副本：extend/lib/host_theme.js
          skills/debug_chrome/extension/shared/host_theme.js

用法：
    python scripts/sync_host_theme.py           # 生成/更新两份副本
    python scripts/sync_host_theme.py --check    # 只校验副本是否与真源一致（CI 用）

退出码：0 = 一致 / 已更新；1 = --check 模式下发现不一致。
"""
import os
import sys

# 工程根：本脚本位于 scripts/ 下，上一级即工程根
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 真源文件
SOURCE = os.path.join(ROOT, "shared", "host_theme.js")
# 两份副本的落点
TARGETS = [
    os.path.join(ROOT, "extend", "lib", "host_theme.js"),
    os.path.join(ROOT, "skills", "debug_chrome", "extension", "shared", "host_theme.js"),
]
# 副本头：标明自动生成，防止有人直接改副本
HEADER = (
    "// 【自动生成，请勿直接编辑】\n"
    "// 本文件由 scripts/sync_host_theme.py 从 shared/host_theme.js 生成。\n"
    "// 需要修改主题探测逻辑时，请改真源 shared/host_theme.js，再运行同步脚本。\n"
)


def render_copy(source_text):
    """把真源内容渲染为副本内容（在顶部插入自动生成头）。"""
    return HEADER + source_text


def main():
    """执行同步或校验。"""
    # --check 模式：只校验不写入
    check_only = "--check" in sys.argv
    # 真源必须存在
    if not os.path.exists(SOURCE):
        print("真源不存在：%s" % SOURCE)
        return 1
    with open(SOURCE, "r", encoding="utf-8") as f:
        source_text = f.read()
    expected = render_copy(source_text)
    # 逐个副本：写入或比对
    dirty = sum(_process_target(t, expected, check_only) for t in TARGETS)
    if check_only:
        if dirty:
            print("\n共 %d 个副本需同步。" % dirty)
            return 1
        print("全部副本与真源一致。")
    return 0


def _process_target(target, expected, check_only):
    """处理单个副本：校验模式下比对，写入模式下覆盖写。

    @param target     副本路径
    @param expected   期望内容
    @param check_only 是否只校验
    @returns 1 表示该副本有问题（缺失 / 不一致），0 表示正常
    """
    if check_only:
        # 校验模式：读现有副本，与期望内容比对
        if not os.path.exists(target):
            print("副本缺失：%s" % os.path.relpath(target, ROOT))
            return 1
        with open(target, "r", encoding="utf-8") as f:
            actual = f.read()
        if actual != expected:
            print("副本与真源不一致：%s" % os.path.relpath(target, ROOT))
            return 1
        return 0
    # 写入模式：确保目录存在后覆盖写入
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="") as f:
        f.write(expected)
    print("已生成：%s" % os.path.relpath(target, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
