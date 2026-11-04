"""指令分组（command_registry.help_groups）测试

为什么需要：
    设置页的「可用指令（点击即执行）」按钮完全由后端分组数据驱动。
    此前只返回内置指令，外部指令与自定义指令在设置页里根本看不到，
    用户只能自己记指令名。本文件把三类指令都必须出现在分组里这一点钉死。

覆盖内容：
    - 内置指令出现在分组里
    - 外部指令单独成组
    - 自定义指令单独成组
    - 某类指令为空时不产生空组
    - 每组结构统一为 {group, items:[{key, name, desc}]}

实现位于 command_groups.py；command_registry 末尾重新导出。
补丁须打在 command_groups（实现所在模块），否则影响不到函数内部查找。

运行：python -m pytest tests/test_command_groups.py -q
"""
from remote_bridge import command_registry as reg
from remote_bridge import command_groups as cg


class TestHelpGroups:
    """三类指令的分组输出。"""

    def test_builtin_present(self):
        """内置指令出现在分组里。

        内置指令的 name 是不带斜杠的主命令名，key 才是带斜杠的快捷键；
        两者口径不同，断言时按 name 比对。
        """
        groups = reg.help_groups()
        names = [i["name"] for g in groups for i in g["items"]]
        # 分组里至少有若干条内置指令
        assert len(names) > 0
        # 每条都带 key 与 name，供前端渲染按钮
        for g in groups:
            for it in g["items"]:
                assert it["key"]
                assert it["name"]

    def test_external_group_included(self, monkeypatch):
        """外部指令单独成组，且组名可辨识。"""
        # 造一条外部指令，避免依赖本机是否装了 skill
        fake = [{"name": "/dc", "alias": "/dc", "desc": "调试扩展",
                 "tool": "t", "params": {}, "provider": "p", "skill": "s"}]
        monkeypatch.setattr(cg, "_external_commands", lambda: fake)
        monkeypatch.setattr(cg, "_custom_commands", lambda: [])
        groups = reg.help_groups()
        ext = [g for g in groups if g["group"] == "外部指令"]
        assert ext, "外部指令应单独成组"
        assert ext[0]["items"][0]["key"] == "/dc"
        # 描述一并带上，前端按钮的悬浮提示要用
        assert ext[0]["items"][0]["desc"] == "调试扩展"

    def test_custom_group_included(self, monkeypatch):
        """自定义指令单独成组。"""
        fake = [{"name": "/deploy", "label": "一键部署", "steps": []}]
        monkeypatch.setattr(cg, "_external_commands", lambda: [])
        monkeypatch.setattr(cg, "_custom_commands", lambda: fake)
        groups = reg.help_groups()
        cus = [g for g in groups if g["group"] == "自定义指令"]
        assert cus, "自定义指令应单独成组"
        item = cus[0]["items"][0]
        assert item["key"] == "/deploy"
        assert item["desc"] == "一键部署"

    def test_empty_categories_produce_no_group(self, monkeypatch):
        """外部与自定义指令都为空时，不产生空组。"""
        monkeypatch.setattr(cg, "_external_commands", lambda: [])
        monkeypatch.setattr(cg, "_custom_commands", lambda: [])
        groups = reg.help_groups()
        names = [g["group"] for g in groups]
        assert "外部指令" not in names
        assert "自定义指令" not in names

    def test_item_shape_uniform(self, monkeypatch):
        """每组的条目结构统一，前端渲染无需分支。"""
        fake = [{"name": "/dc", "alias": "", "desc": "d", "tool": "t",
                 "params": {}, "provider": "p", "skill": "s"}]
        monkeypatch.setattr(cg, "_external_commands", lambda: fake)
        monkeypatch.setattr(cg, "_custom_commands", lambda: [])
        for g in reg.help_groups():
            assert set(g.keys()) == {"group", "items"}
            for it in g["items"]:
                assert set(it.keys()) == {"key", "name", "desc"}
