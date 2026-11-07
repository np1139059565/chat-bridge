"""内置指令 /new1：新建会话并接续任务。

背景：/new1 原先是 definition.yaml 里的自定义组合指令（步骤 /new → /csp → /sa on），
用户一旦在设置页误删就整条消失。现提权为内置，代码里恒定存在。

本文件锁住三条约束：
  1. /new1 同时出现在指令表与处理函数表，且导入自检能通过；
  2. 步骤定义固定为三步、间隔 5 秒，不随自定义配置变动；
  3. 各步骤能被正常解析（内置或自定义），不会出现某步无处可去。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from remote_bridge import command_panel as cp  # noqa: E402
from remote_bridge.command_registry import BUILTIN, resolve_cmd  # noqa: E402


def test_new1_registered_as_builtin():
    """指令表与分发表都必须有 /new1。"""
    assert "/new1" in BUILTIN
    assert "/new1" in cp._BUILTIN_HANDLERS


def test_handler_table_consistent():
    """两张表必须一一对应——导入期自检不抛异常即为通过。"""
    cp._check_handler_table()


def test_new1_steps_are_fixed():
    """步骤与间隔写死在代码里，不受自定义配置影响。"""
    assert cp._NEW1_ENTRY["steps"] == ["/new", "/csp", "/sa on"]
    assert cp._NEW1_ENTRY["interval"] == 5


def test_each_step_resolves():
    """每一步都要能落地：要么命中内置，要么能落到自定义指令表。

    /new 是站点点击指令，刻意留在 definition.yaml 的自定义区
    （选择器随站点改版调整，不适合写死在代码里），
    故此处只断言它能被解析成命令名，不要求它是内置。
    """
    for step in cp._NEW1_ENTRY["steps"]:
        head = step.split()[0]
        resolved = resolve_cmd(head.lower())
        assert resolved, "步骤无法解析：" + step
        is_builtin = resolved in cp._BUILTIN_HANDLERS
        is_custom_name = resolved.startswith("/")
        assert is_builtin or is_custom_name, "步骤无处可去：" + step


def test_copy_and_auto_are_builtin():
    """后两步必须是内置，避免依赖自定义配置而失效。"""
    assert resolve_cmd("/csp") in cp._BUILTIN_HANDLERS
    assert resolve_cmd("/sa") in cp._BUILTIN_HANDLERS
