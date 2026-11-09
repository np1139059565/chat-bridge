const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const R = (f) => path.join(__dirname, '..', '..', '..', f);
const P = (f) => R('extend/dialog/parts/' + f);
const rd = (f) => fs.readFileSync(R(f), 'utf8');

test('串号已修：renderConfigBadge 函数体按段计数，不含全局计数', () => {
  const s = rd('extend/dialog/parts/08j_config_actions.js');
  const a = s.indexOf('D.renderConfigBadge = function');
  // 只取这一个函数体：末尾追加的 renderSiteProfileBadge 与状态栏都不在范围内。
  const z = s.indexOf(String.fromCharCode(10) + '  };', a);
  const seg = s.slice(a, z > 0 ? z : s.length);
  assert.ok(seg.indexOf('section ===') >= 0);
  assert.ok(seg.indexOf('configDiffCount') < 0);
});

test('卡片头归属：工具 / 通用 / 站点各自挂专属徽标', () => {
  assert.ok(rd('extend/dialog/parts/08b_settings.js').indexOf("renderConfigBadge(ctx, 'tools')") >= 0);
  assert.ok(rd('extend/dialog/parts/08_settings.js').indexOf("renderConfigBadge(ctx, 'general')") >= 0);
  assert.ok(rd('extend/dialog/parts/08g_site_profiles.js').indexOf('renderSiteProfileBadge') >= 0);
});

test('bridge 徽标不重复挂（远程桥接与投递策略曾挂两次）', () => {
  const s = rd('extend/dialog/parts/08b_settings.js');
  assert.strictEqual((s.match(/renderBlockBadge\(ctx, 'bridge'\)/g) || []).length, 1);
});

test('CONFIG_BLOCKS 每个 id 都在设置页挂了徽标', () => {
  const s = rd('extend/dialog/parts/08b_settings.js');
  const k = rd('extend/dialog/parts/08k_config_blocks.js');
  const ids = [...k.matchAll(/id: '([a-z_]+)'/g)].map((m) => m[1]);
  assert.ok(ids.length >= 7);
  for (const id of ids) {
    assert.ok(s.indexOf("'" + id + "'") >= 0, id + ' 未挂徽标');
  }
});

test('QQ / 企业微信输入框：data-diff 标色 + markBlockField 登记', () => {
  for (const f of ['extend/dialog/parts/08c_bridge.js',
    'extend/dialog/parts/08e_bridge_wecom.js']) {
    const s = rd(f);
    assert.strictEqual((s.match(/data-diff/g) || []).length, 2, f + ' 标色数');
    assert.strictEqual((s.match(/markBlockField/g) || []).length, 2, f + ' 登记数');
  }
});

test('草稿态保存不再谎报「已保存并重启」', () => {
  for (const f of ['extend/dialog/parts/01b_bridge.js',
    'extend/dialog/parts/01h_bridge_wecom.js',
    'extend/dialog/parts/01f_bridge_weixin.js']) {
    const s = rd(f);
    assert.ok(s.indexOf('settleBlockFields') >= 0, f + ' 未 settle');
    assert.ok(s.indexOf('data.draft') >= 0, f + ' 未判草稿态');
  }
});

test('UI 源码不再出现「与服务端一致」报平安文案', () => {
  for (const f of ['extend/dialog/parts/08j_config_actions.js',
    'extend/dialog/parts/08b_settings.js', 'extend/dialog/parts/08_settings.js']) {
    assert.strictEqual(rd(f).indexOf('与服务端' + '一致'), -1, f);
  }
});

test('blockFields 是内部字段，不进公共配置比对与提交体', () => {
  const s = rd('extend/dialog/parts/08i_config_cache.js');
  assert.ok(s.indexOf("k !== 'blockFields'") >= 0);
  assert.ok(s.indexOf('delete out.blockFields;') >= 0);
});

test('审计清单：打印未接追踪的 onInput，供人工复核是否属配置类', () => {
  const out = [];
  for (const f of fs.readdirSync(R('extend/dialog/parts'))) {
    if (!f.endsWith('.js')) continue;
    const ls = rd('extend/dialog/parts/' + f).split(String.fromCharCode(10));
    ls.forEach((l, i) => {
      if (l.indexOf('onInput') >= 0
        && l.indexOf('markBlockField') < 0
        && l.indexOf('queueSiteProfSave') < 0
        && l.indexOf('ctx.newSite') < 0) out.push(f + ':' + (i + 1));
    });
  }
  console.log('AUDIT_ONINPUT=' + out.join(','));
  assert.ok(Array.isArray(out));
});

test('统一输入追踪：入口已安装，所有受管区块都有容器', () => {
  const b = rd('extend/dialog/parts/08b_settings.js');
  const l = rd('extend/dialog/parts/08l_config_field_tracking.js');
  assert.ok(b.indexOf('installConfigFieldTracking') >= 0);
  assert.ok(l.indexOf('focusin') >= 0);
  assert.ok(l.indexOf('pointerdown') >= 0);
  assert.ok(l.indexOf("addEventListener('input'") >= 0);
  assert.ok(l.indexOf("addEventListener('change'") >= 0);
  const k = rd('extend/dialog/parts/08k_config_blocks.js');
  const s8 = rd('extend/dialog/parts/08_settings.js');
  const ids = [...k.matchAll(/id: '([a-z_]+)'/g)].map((m) => m[1]);
  for (const id of ids) {
    if (id === 'custom_tools' || id === 'general') {
      assert.ok(s8.indexOf("'data-cfg-block': '" + id + "'") >= 0, id + ' 未包容器');
    } else {
      assert.ok(b.indexOf("'data-cfg-block': '" + id + "'") >= 0, id + ' 未包容器');
    }
  }
});

test('工具内部配置不被提交体污染：深拷贝 + 自愈 + 渲染兜底三处齐备', () => {
  assert.ok(rd('extend/dialog/parts/08i_config_cache.js').indexOf('JSON.parse(JSON.stringify(v))') >= 0);
  assert.ok(rd('extend/dialog/parts/08j_config_actions.js').indexOf('healSpecs') >= 0);
  assert.ok(rd('extend/dialog/parts/08e_toolconf.js').indexOf('Array.isArray(rows)') >= 0);
});

test('所有 renderConfigBadge 调用都带 section 参数，杜绝回退到全局口径', () => {
  for (const f of ['extend/dialog/parts/08b_settings.js',
    'extend/dialog/parts/08_settings.js']) {
    const s = rd(f);
    assert.strictEqual((s.match(/renderConfigBadge\(ctx\)/g) || []).length, 0, f);
  }
});

test('局部渲染文件源码内不得出现全局差异计数', () => {
  for (const f of ['extend/dialog/parts/08b_settings.js',
    'extend/dialog/parts/08_settings.js',
    'extend/dialog/parts/08g_site_profiles.js']) {
    assert.strictEqual(rd(f).indexOf('configDiffCount'), -1, f);
  }
});

test('工具内部配置三层防护齐备：深拷贝 / 自愈 / 渲染兜底', () => {
  assert.ok(rd('extend/dialog/parts/08i_config_cache.js').indexOf('JSON.parse(JSON.stringify(v))') >= 0);
  const j = rd('extend/dialog/parts/08j_config_actions.js');
  assert.ok(j.indexOf('healSpecs') >= 0);
  assert.ok(j.indexOf('typeof curSys') >= 0);
  const e = rd('extend/dialog/parts/08e_toolconf.js');
  assert.strictEqual((e.match(/Array.isArray\(rows\)/g) || []).length, 2);
});

test('站点配置块徽标不重复：08g 挂专属徽标，08b 不再另挂', () => {
  assert.ok(rd('extend/dialog/parts/08g_site_profiles.js').indexOf('renderSiteProfileBadge') >= 0);
  const b = rd('extend/dialog/parts/08b_settings.js');
  assert.strictEqual((b.match(/renderBlockBadge\(ctx, 'site_profiles'\)/g) || []).length, 0);
});

test('浮层逐项确认：确认框改 fixed 浮层，伪差异字段已剔除', () => {
  const b = rd('extend/dialog/parts/08b_settings.js');
  const j = rd('extend/dialog/parts/08j_config_actions.js');
  const i = rd('extend/dialog/parts/08i_config_cache.js');
  assert.ok(b.indexOf('D.renderConfigConfirmBar') >= 0);
  assert.ok(j.indexOf('sp-modal-mask') >= 0);
  assert.ok(j.indexOf('configDiffItems') >= 0);
  assert.ok(i.indexOf("k !== 'available_tools'") >= 0);
  assert.ok(i.indexOf("k !== 'site_profiles'") >= 0);
});

test('渲染层 hosts 不再直接 String(val)', () => {
  assert.strictEqual(rd('extend/dialog/parts/08g_site_profiles.js').indexOf('String(val)'), -1);
});

test('08g 自带文本归一化：单独渲染不因 08j 未加载而抛错', () => {
  const g = rd('extend/dialog/parts/08g_site_profiles.js');
  assert.ok(g.indexOf('const toText') >= 0);
  assert.strictEqual(g.indexOf('D.configValueToText(val)'), -1);
});
