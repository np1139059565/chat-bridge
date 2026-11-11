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
test('指令瞬态表单排除追踪，历史残留也不计入差异',()=>{
 assert.ok(rd('extend/dialog/parts/08b_settings.js').indexOf("'data-cfg-block': 'commands', 'data-cfg-skip': ''")>=0);
 assert.ok(rd('extend/dialog/parts/08j_config_actions.js').indexOf('if (bf.commands) delete bf.commands;')>=0);
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
 assert.ok(b.indexOf('configLoadAndDiff(this.configBackend)')>=0);
 assert.ok(b.indexOf('resetSiteProfDraft()')>=0);
});
test('行数门禁：00_data / 01_backend / 08b / 08j / 08l 均不超过 450 行',()=>{
 ['00_data.js','01_backend.js','08b_settings.js','08j_config_actions.js','08l_config_field_tracking.js'].forEach(f=>{
  const n=rd('extend/dialog/parts/'+f).split(NL).length;assert.ok(n<=450,f+' 行数 '+n);});
});
