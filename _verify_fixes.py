"""验证两个问题的修复：工具必填参数校验 + /config 端口变更 requireRestart。"""
import sys, importlib.util
sys.path.insert(0, 'flask_server')
spec = importlib.util.spec_from_file_location('srv', 'flask_server/server.py')
srv = importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
impl = srv.impl  # 工具实现在 tools_impl 模块

# 1) 必填参数校验：AI 用错名 path 调 list_dir 必须抛 parameter 错误（不再静默用 cwd）
try:
    impl.t_list_dir({'path': 'D:\\projects\\yuxiaoxing-app'})
    print('FAIL: list_dir(path=...) 未报错（仍会静默返回 cwd）')
except impl.ToolParamError as e:
    print('OK: list_dir(path=...) 抛 parameter 错误 ->', str(e)[:70], '...')

r = impl.t_list_dir({'target_directory': 'flask_server'})
print('OK: list_dir(target_directory) 正常，directory =', r['directory'])

try:
    impl.t_delete_file({})
    print('FAIL: delete_file 缺参未报错')
except impl.ToolParamError:
    print('OK: delete_file 缺参抛 parameter 错误')

# 2) /config 端口变更应返回 requireRestart
client = srv.app.test_client()
g = client.get('/config'); cfg = g.get_json()
print('GET /config 当前端口 =', cfg['flask']['port'])
p = client.post('/config', json={'flask': {'port': 8080}})
jd = p.get_json()
print('POST /config port=8080 -> requireRestart =', jd.get('requireRestart'), 'changed =', jd.get('changed'))
assert jd.get('requireRestart') is True, '端口变更必须标记 requireRestart'
client.post('/config', json={'flask': {'port': 5000}})
srv.CONFIG['flask']['port'] = 5000
p2 = client.post('/config', json={'tools': {'read_file': {'enabled': False}}})
assert p2.get_json().get('requireRestart') is False, '工具上下线不应 requireRestart'
client.post('/config', json={'tools': {'read_file': {'enabled': True}}})
print('OK: 工具上下线 requireRestart =', p2.get_json().get('requireRestart'))
print('ALL OK')
