"""工程质量检查 —— 兼容入口（薄转发）

本脚本曾是独立的三项检查（超大文件 / 超长函数 / 重复块）。
现在这三项已并入统一闸门 quality_rules.py（实现见 quality_extra.py），
此处只做转发，保证旧调用方与文档里的命令仍能跑通。

为什么不直接删：它是被 README 与多份文档引用的命令名，
删除会让照着文档敲命令的人扑空；薄转发既保住入口，又只有一份实现。

请改用统一入口：python scripts/quality_rules.py
（钩子与 CI 均已改跑该脚本，十二项规则 + 存量基线）
"""
import os
import sys

# scripts/ 自身在导入路径上：直接导入同级模块
import quality_rules


def main():
    """转发到统一闸门。

    退出码语义与原来一致：0 = 无新增违规；1 = 有新增违规。
    @returns 进程退出码
    """
    print("[提示] check_quality.py 已并入统一闸门，请改用：python scripts/quality_rules.py\n")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return quality_rules.main([root])


if __name__ == "__main__":
    sys.exit(main())
