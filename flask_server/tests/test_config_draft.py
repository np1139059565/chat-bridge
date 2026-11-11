import copy
import tempfile
import unittest
from pathlib import Path
from flask import Flask
import config_draft_store as ds
from routes import config_route as cr
import runtime

ROOT = Path(__file__).resolve().parents[2]

class TestConfigDraft(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = ds._DRAFT_DIR
        ds._DRAFT_DIR = Path(self.tmp.name)
        cr._MASTER_CACHE = None
        self.cfg_bak = copy.deepcopy(runtime.CONFIG)
        self.app = Flask(__name__)
        self.app.register_blueprint(cr.bp)
        self.c = self.app.test_client()

    def tearDown(self):
        ds._DRAFT_DIR = self.old
        cr._MASTER_CACHE = None
        runtime.CONFIG.clear()
        runtime.CONFIG.update(self.cfg_bak)
        self.tmp.cleanup()

    def H(self, site):
        return {'X-Site-Key': site}

    def test_1_default_empty_first_visit_copies_master(self):
        self.assertEqual(list(ds._DRAFT_DIR.glob('*.json')), [], '草稿默认不该预建')
        j = self.c.get('/config/draft', headers=self.H('new.com')).get_json()
        self.assertEqual(j['site'], 'new.com')
        self.assertEqual(j['draft'], j['master'], '首次应从母版拷贝')
        self.assertEqual(len(list(ds._DRAFT_DIR.glob('*.json'))), 1, '首次才生成一份')

    def test_2_other_site_gets_clean_master(self):
        m = self.c.get('/config/draft', headers=self.H('a.com')).get_json()['master']
        d = self.c.get('/config/draft', headers=self.H('a.com')).get_json()['draft']
        d['limits'] = {'max_json_chars': 555}
        r = self.c.post('/config/draft', json=d, headers=self.H('a.com'))
        self.assertTrue(r.get_json()['success'])
        j2 = self.c.get('/config/draft', headers=self.H('b.com')).get_json()
        self.assertEqual(j2['master'], m, '母版被草稿污染')
        self.assertEqual(j2['draft'], m, 'B 站首次应拿母版')
        self.assertNotEqual(j2['draft']['limits']['max_json_chars'], 555, 'B 站带到 A 站改动')
        self.assertEqual(ds.load('a.com')['limits']['max_json_chars'], 555)

    def test_3_site_isolation_direct(self):
        ds.save('a.com', {'x': 1})
        ds.save('b.com', {'x': 2})
        self.assertEqual(ds.load('a.com')['x'], 1)
        self.assertEqual(ds.load('b.com')['x'], 2)
        ds.clear('a.com')
        self.assertIsNone(ds.load('a.com'))
        self.assertEqual(ds.load('b.com')['x'], 2)

    def test_4_post_apply_and_get_replay_after_restart(self):
        d = self.c.get('/config/draft', headers=self.H('a.com')).get_json()['draft']
        d['limits'] = {'max_json_chars': 321}
        r = self.c.post('/config/draft', json=d, headers=self.H('a.com'))
        self.assertTrue(r.get_json()['success'])
        self.assertEqual(runtime.CONFIG['limits']['max_json_chars'], 321, '改完未即时生效')
        runtime.CONFIG.setdefault('limits', {})['max_json_chars'] = 1
        self.c.get('/config/draft', headers=self.H('a.com'))
        self.assertEqual(runtime.CONFIG['limits']['max_json_chars'], 321, '重启后未重放')

    def test_5_draft_change_never_writes_master(self):
        j8 = (ROOT / 'extend' / 'dialog' / 'parts' / '08j_config_actions.js').read_text(encoding='utf-8')
        self.assertNotIn('if (D.apiFetch && path)', j8, '草稿态仍调原端点写母版')
        st = Path(cr.__file__).read_text(encoding='utf-8')
        seg = st.split('def config_draft()')[1].split('@bp.route')[0]
        self.assertNotIn('save_config_to_yaml', seg, '草稿 POST 写了母版 yaml')

    def test_6_source_audit(self):
        st = Path(cr.__file__).read_text(encoding='utf-8')
        self.assertIn('init_from_master(site, master)', st)
        self.assertIn('copy.deepcopy(_config_snapshot())', st)
        self.assertIn('_MASTER_CACHE = None', st)
        self.assertIn('X-Site-Key', st)
        self.assertIn('draft_store.apply_to_runtime(d)', st)
        sd = Path(ds.__file__).read_text(encoding='utf-8')
        self.assertIn('def init_from_master', sd)
        self.assertIn('def apply_to_runtime', sd)

if __name__ == '__main__':
    unittest.main()
