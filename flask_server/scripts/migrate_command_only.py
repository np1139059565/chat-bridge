"""AI 工具调用镜像插件 —— 一次性迁移：command_only → kind: command_action

背景：
    早期设计把「指令执行端」和「AI 工具」混放在同一份工具定义里，用
    command_only: true 标记前者。这导致指令信息易混入 AI 工具目录。
    现改为「源头分开」：由解析层按来源数组自动标注 kind（tool / command_action），
    不再使用人工标记。本脚本把已落库的旧数据一次性迁移到新字段。

做法：
    扫描配置的 custom_tools 分区（definition.yaml），把每条工具定义里
    的 command_only: true 改写为 kind: command_action；其余字段不动。
    幂等：已无 command_only 时不改动。

用法：
    python scripts/migrate_command_only.py
"""
import io
import sys

import paths


def migrate_file(path):
    """对单个 YAML 文件做行级迁移，返回改写的行数。

    @param path 目标文件路径（Path）
    @return 改写的行数（0 表示无需迁移）
    """
    if not path.exists():
        return 0
    lines = io.open(str(path), encoding="utf-8").read().splitlines(keepends=True)
    out = []
    changed = 0
    for ln in lines:
        # 只改缩进后的工具字段行：    command_only: true
        if ln.strip() == "command_only: true":
            indent = ln[:len(ln) - len(ln.lstrip())]
            out.append(indent + "kind: command_action\n")
            changed += 1
        else:
            out.append(ln)
    if changed:
        io.open(str(path), "w", encoding="utf-8").write("".join(out))
    return changed


def main():
    """迁移配置中的自定义工具定义。

    definition.yaml 存放工具定义（入库）；runtime.yaml 只存开关，无需迁移。
    """
    targets = [paths.DEFINITION_PATH]
    total = 0
    for p in targets:
        n = migrate_file(p)
        total += n
        print("迁移 %s：改写 %d 行" % (p, n))
    print("完成，共改写 %d 行。" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
