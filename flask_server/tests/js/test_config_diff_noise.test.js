'use strict';
global.window = { AIMirrorDialog: { methods: {}, log: function () {} } };
global.Vue = { h: function () { return { tag: 'x' }; } };
var base = 'E:/projects/chat-bridge-main/extend/dialog/parts/';
require(base + '08i_config_cache.js');
require(base + '08j_config_actions.js');
var D = window.AIMirrorDialog;
var assert = require('assert');
var backend = {
  flask: { host: '127.0.0.1', port: 5000, url: 'http://127.0.0.1:5000' },
  limits: { max_json_chars: 100000 }, tools: { read_file: { enabled: true } },
  tool_config: {}, system_config: [], default_profile: 'glm',
  profiles: {}, site_profiles: {}, available_tools: [],
  pending: [], blocks: {}, overrides: {}, blockFields: {}, config_draft: { foo: 1 }, _extra: 'noise'
};
var cache = JSON.parse(JSON.stringify(backend));
cache.config_draft = { foo: 2 }; cache._extra = 'noise2'; cache.pending = [{ path: '/x' }];
var pb = D.configPublic(backend), pc = D.configPublic(cache), pd = {};
Object.keys(pc).concat(Object.keys(pb)).forEach(function (k) {
  if (JSON.stringify(pc[k]) !== JSON.stringify(pb[k])) pd[k] = 1;
});
assert.strictEqual(Object.keys(pd).length, 0, 'configPublic 不应把派生键算成差异');
var ctx = { configBackend: backend, configOffline: false,
  configDiffItems: [{ section: 'general', block: 'general', label: '公共配置 · flask',
    detail: '整份提交，影响所有页面与电脑', key: 'flask' }] };
assert.strictEqual(D.renderConfigBadge(ctx, 'general'), null, '卡片头不应重复挂公共汇总徽标');
console.log('OK 2 assertions');
