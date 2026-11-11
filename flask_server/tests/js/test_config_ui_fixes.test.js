// 模块：配置 UI 四处修正的回归测试
const test=require('node:test');const assert=require('node:assert');
const fs=require('node:fs');const path=require('node:path');
const R=(f)=>path.join(__dirname,'..','..','..',f);
const rd=(f)=>fs.readFileSync(R(f),'utf8');const NL=String.fromCharCode(10);
test('块头徽标归位：容器加 sp-block-wrap，CSS 绝对定位到标题行',()=>{
 const b=rd('extend/dialog/parts/08b_settings.js');
 const ids=[...b.matchAll(/'data-cfg-block': '([a-z_]+)'/g)].map(m=>m[1]);
 assert.ok(ids.length>=7);
 ids.forEach(id=>{const l=b.split(NL).find(x=>x.indexOf("'data-cfg-block': '"+id+"'")>=0);assert.ok(l&&l.indexOf('sp-block-wrap')>=0,id+' 未加定位容器');});
 const c=rd('extend/dialog/styles/02f_site_profiles.css');
 assert.ok(c.indexOf('.sp-block-wrap { position: relative; }')>=0);
 assert.ok(c.indexOf('.sp-block-wrap > .sp-diff-badge')>=0);
});
test('指令覆盖检测：仅编辑态输入被追踪，非编辑态列表不检测',()=>{
 const b=rd('extend/dialog/parts/08b_settings.js');
 assert.ok(b.indexOf("'data-cfg-block': 'commands'")>=0);
 assert.ok(b.indexOf("'data-cfg-block': 'commands', 'data-cfg-skip'")<0,'指令块仍被整体排除');
 const j=rd('extend/dialog/parts/08j_config_actions.js');
 assert.ok(j.indexOf('delete bf.commands')<0,'commands 差异仍被丢弃');
 assert.ok(rd('extend/dialog/parts/08l_config_field_tracking.js').indexOf('D.markBlockField(ctx, rec.id')>=0);
 const f=rd('extend/dialog/parts/08f_commands.js');
 assert.ok(f.indexOf('bridgeEditIdx === null')>=0,'新建态未动态排除');
 assert.ok(f.indexOf('editProps')>=0,'编辑态属性容器缺失');
});
test('差异字段显式进初始 state，输入后强制重渲染',()=>{
 const d=rd('extend/dialog/parts/00_data.js');
 assert.ok(d.indexOf('configDiffItems: []')>=0);
 assert.ok(d.indexOf('configBlockDirty: {}')>=0);
 assert.ok(d.indexOf('configDiffCount: 0')>=0);
 assert.ok(rd('extend/dialog/parts/08l_config_field_tracking.js').indexOf('$forceUpdate')>=0);
});
test('切站：空 siteKey 不覆盖，切换后按新站点重建配置与草稿',()=>{
 const b=rd('extend/dialog/parts/01_backend.js');
 assert.ok(b.indexOf('if (!k || k === this.siteKey) return;')>=0);
 assert.ok(b.indexOf('this.loadConfig()')>=0,'切站未重拉 /config/draft 两份配置');
 assert.ok(b.indexOf('resetSiteProfDraft()')>=0);
});
test('行数门禁：00_data / 01_backend / 08b / 08j / 08l 均不超过 450 行',()=>{
 ['00_data.js','01_backend.js','08b_settings.js','08j_config_actions.js','08l_config_field_tracking.js'].forEach(f=>{
  const n=rd('extend/dialog/parts/'+f).split(NL).length;assert.ok(n<=450,f+' 行数 '+n);});
});
