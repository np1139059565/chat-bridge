"""P1 regression: max_json_chars prefers runtime.CONFIG immediate value."""
# 该用例不依赖真实 Flask 进程，只注入两个外部模块。
# runtime 模拟 apply_to_runtime 已灌入的内存值。
# yaml_utils 模拟磁盘母版，作为启动兜底。
# 三组断言分别覆盖：内存优先、重启回退、体积三态。
import importlib.util
import json
import os
import sys
import types
import unittest

# 将源码目录加入检索路径，避免依赖包安装状态。
HERE = os.path.dirname(os.path.abspath(__file__))
SRV = os.path.normpath(os.path.join(HERE, '..'))
TOOLS = os.path.join(SRV, 'tools')
REL = os.path.join(TOOLS, 'tool_helpers.py')
for p in (TOOLS, SRV, os.path.join(SRV, 'core')):
    if p not in sys.path:
        sys.path.insert(0, p)


def load(rv, yv):
    """每次重新加载模块，确保读到本次注入的 runtime 值。"""
    for n in ('runtime', 'yaml_utils'):
        sys.modules.pop(n, None)
    rt = types.ModuleType('runtime')
    # 内存值缺省时留空字典，走磁盘回退分支。
    rt.CONFIG = {'limits': {'max_json_chars': rv}} if rv else {}
    sys.modules['runtime'] = rt
    yu = types.ModuleType('yaml_utils')
    yu.load_config_dict = lambda: ({'limits': {'max_json_chars': yv}} if yv else {})
    sys.modules['yaml_utils'] = yu
    spec = importlib.util.spec_from_file_location('th_%s_%s' % (rv, yv), REL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class T(unittest.TestCase):
    """三组用例：优先级、回退、体积三态。"""

    def test_memory_wins(self):
        # 内存 3000 应压过磁盘 100000。
        self.assertEqual(load(3000, 100000).max_json_chars(), 3000)

    def test_yaml_fallback(self):
        # 内存无值（重启后）应回退到磁盘 200000。
        self.assertEqual(load(None, 200000).max_json_chars(), 200000)

    def test_three_states(self):
        # 未超限原样返回。
        self.assertEqual(load(3000, 100000).enforce_size_limit({'x': 'a'}, 'g'), {'x': 'a'})
        # 超限抛错而非截断，避免不完整结果进 AI。
        self.assertRaises(Exception, load(3000, 100000).enforce_size_limit, {'x': 'a' * 4000}, 'g')
        # 恰好等于上限应放行；字符数按 JSON 序列化结果计。
        n = 2990
        while len(json.dumps({'x': 'a' * n}, ensure_ascii=False)) < 3000:
            n += 1
        eq = {'x': 'a' * n}
        self.assertEqual(load(3000, 100000).enforce_size_limit(eq, 'g'), eq)


if __name__ == '__main__':
    unittest.main()
