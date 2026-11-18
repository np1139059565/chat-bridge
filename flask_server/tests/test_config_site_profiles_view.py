"""P2 regression: per-site profiles view must not leak across pages."""
# 直接测草稿存储层的按站视图，不依赖 Flask 进程。
# 用临时目录隔离草稿文件，避免污染真实 config/drafts。
# 两组用例：A 站改动不外溢到 B 站；同站点改动正常覆盖。
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SRV = os.path.normpath(os.path.join(HERE, '..'))
if SRV not in sys.path:
    sys.path.insert(0, SRV)
import config_draft_store as ds


class T(unittest.TestCase):
    """跨站隔离与同站覆盖两态。"""

    def setUp(self):
        # 每次用独立临时目录，避免用例间草稿互相影响。
        self.tmp = tempfile.mkdtemp()
        self.origin = ds._DRAFT_DIR
        ds._DRAFT_DIR = Path(self.tmp)
        self.master = {
            'profiles': {
                'glm': {'name': 'GLM', 'hosts': ['chatglm.cn']},
                'ds': {'name': 'DS', 'hosts': ['chat.deepseek.com']},
            }
        }

    def tearDown(self):
        # 还原全局草稿目录，不影响其他测试。
        ds._DRAFT_DIR = self.origin

    def test_cross_site_isolation(self):
        # A 站改 glm 档案后，B 站视图必须仍是母版值。
        ds.save('a.com', {'profiles': {'glm': {'name': 'GLM-A', 'hosts': ['chatglm.cn']}}})
        va, _ = ds.site_profiles_view('a.com', self.master)
        vb, _ = ds.site_profiles_view('b.com', self.master)
        self.assertEqual(va['glm']['name'], 'GLM-A')
        self.assertEqual(vb['glm']['name'], 'GLM')
        # 未提交档案原样保留，确认 D2 合并语义没被破坏。
        self.assertIn('ds', vb)

    def test_same_site_overwrite(self):
        # 同站点改动必须即时反映在该站视图里。
        ds.save('a.com', {'profiles': {'glm': {'name': 'X', 'hosts': ['chatglm.cn']}}})
        va, _ = ds.site_profiles_view('a.com', self.master)
        self.assertEqual(va['glm']['name'], 'X')


if __name__ == '__main__':
    unittest.main()
