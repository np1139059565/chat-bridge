const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

global.window = { AIMirrorDialog: { methods: {} } };
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '08i_config_cache.js'));
const D = global.window.AIMirrorDialog;
const NL = String.fromCharCode(10);

test('configCacheKey：按站点分键，空值兜底', () => {
  assert.strictEqual(D.configCacheKey('glm'), 'aiMirrorConfigCache_glm');
  assert.strictEqual(D.configCacheKey(''), 'aiMirrorConfigCache_unknown-site');
});

test('configCache Get/Set：node 环境走内存降级，刷新不丢本地值', async () => {
  await D.configCacheSet('siteA', { limits: { max_json_chars: 123 } });
  const got = await D.configCacheGet('siteA');
  assert.deepStrictEqual(got, { limits: { max_json_chars: 123 } });
  const other = await D.configCacheGet('siteB');
  assert.strictEqual(other, null);
});

test('configPublic：剔除 profiles，保留其余全部顶层键（D3 全存口径）', () => {
  const pub = D.configPublic({
    flask: { port: 5000 }, limits: { max_json_chars: 1 },
    profiles: { glm: { label: 'G' } }, tools: {}, available_tools: ['x']
  });
  assert.ok(!('profiles' in pub));
  assert.deepStrictEqual(pub.limits, { max_json_chars: 1 });
  assert.deepStrictEqual(pub.available_tools, ['x']);
});

test('configFieldToText：数组 / 布尔 / 多行文本归一，空值转空串', () => {
  assert.strictEqual(D.configFieldToText([' a.com ', '', 'b.com']), 'a.com' + NL + 'b.com');
  assert.strictEqual(D.configFieldToText(true), 'true');
  assert.strictEqual(D.configFieldToText(false), 'false');
  assert.strictEqual(D.configFieldToText(null), '');
  assert.strictEqual(D.configFieldToText('  .x  ' + NL + '  .y  '), '.x' + NL + '.y');
});

test('profileToDraft：数组转按行文本，布尔保留', () => {
  const d = D.profileToDraft({
    label: 'GLM', hosts: ['a.com', 'b.com'],
    generatingSelectors: ['.x', '.y'], split: false
  });
  assert.strictEqual(d.hosts, 'a.com' + NL + 'b.com');
  assert.strictEqual(d.generatingSelectors, '.x' + NL + '.y');
  assert.strictEqual(d.split, false);
});

test('profileFieldDiff：逐字段比，返回后端值；N1 无基准，自己改的也会标色', () => {
  const local = { label: 'GLM', hosts: 'a.com' + NL + 'b.com', container: '.mine' };
  const backend = { label: 'GLM', hosts: ['a.com', 'b.com'], container: '.server' };
  const diff = D.profileFieldDiff(local, backend);
  assert.deepStrictEqual(Object.keys(diff).sort(), ['container']);
  assert.strictEqual(diff.container, '.server');
  // 后端有、本地没有的字段也算不一致
  const d2 = D.profileFieldDiff({ a: '1' }, { a: '1', b: '2' });
  assert.strictEqual(d2.b, '2');
});

test('configPublicToBody：spec 数组扁平化、system 合入、派生字段删除', () => {
  const body = D.configPublicToBody({
    flask: { host: '127.0.0.1', port: 5000, url: 'http://x' },
    limits: { max_json_chars: 1000 },
    tool_config: { read_file: [{ key: 'max_bytes', value: 42 }] },
    system_config: [{ key: 'queue_max', value: 7 }],
    available_tools: ['read_file'], site_profiles: { 'a.com': 'glm' }
  });
  assert.strictEqual(body.tool_config.read_file.max_bytes, 42);
  assert.strictEqual(body.tool_config.system.queue_max, 7);
  assert.ok(!('system_config' in body));
  assert.ok(!('available_tools' in body));
  assert.ok(!('site_profiles' in body));
  assert.deepStrictEqual(body.limits, { max_json_chars: 1000 });
});
