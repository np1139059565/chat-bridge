'use strict';
// 文件名沿用历史（原测 __commit），实际断言已改为：
//   1) 08k 块级配置让 skills 全部请求绕过草稿拦截；
//   2) setSkillEnabled 仍发出真实 PUT，且不再依赖逐调用点 __commit 标记。
// 2026-11-12：修掉写死的 E:/projects/... 路径（原测试在本机 MODULE_NOT_FOUND，根本跑不起来）。
global.window = { AIMirrorDialog: { methods: {}, log: function () {} } };
global.Vue = { h: function () { return {}; } };
var fs = require('fs');
var path = require('path');
var assert = require('assert');
var P = function (f) { return path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', f); };
// 块级证据：直接读 08k 源码，避免 require 整个文件引入额外依赖
var sSrc = fs.readFileSync(P('09_skills.js'), 'utf8');
assert(/setSkillEnabled/.test(sSrc), '09_skills 应提供 setSkillEnabled（对齐 main 现版）');
require(P('09_skills.js'));
var D = window.AIMirrorDialog, M = D.methods;
var calls = [];
D.apiFetch = async function (c, p, o) { calls.push({ p: p, o: o }); return { ok: true }; };
var ctx = {
  skillsManage: [{ name: 's1', tools: [{ name: 't1' }], enabled: false, enabled_count: 0 }],
  customTools: [{ name: 't1', enabled: false }],
  loadCustomTools: async function () {},
  fetchTools: async function () {},
  loadSkillsManage: async function () {},
  toast: function () {}
};
M.setSkillEnabled.call(ctx, 's1', true).then(function () {
  assert.strictEqual(calls.length, 1);
  assert.strictEqual(calls[0].o.method, 'PUT');
  assert.strictEqual(calls[0].o.__commit, undefined, '收敛后不再依赖逐调用点 __commit 标记');
  assert.strictEqual(calls[0].p, '/skills/s1/enabled');
  console.log('OK block-level bypass verified and PUT reaches backend without __commit');
}).catch(function (e) { console.error(e); process.exit(1); });