// 模块：配置副本全局单键 / 刷新不丢 / 旧分桶快照自愈 的回归测试
const test=require('node:test');const assert=require('node:assert');
const fs=require('node:fs');const path=require('node:path');
const P=(f)=>path.join(__dirname,'..','..','..','extend','dialog','parts',f);
const S={};
global.chrome={storage:{local:{
 get:function(keys,cb){if(typeof keys==='function'){cb=keys;keys=null;}
  var r={};if(keys===null){Object.keys(S).forEach(function(k){r[k]=S[k];});}
  else{(Array.isArray(keys)?keys:[keys]).forEach(function(k){if(S[k]!==undefined)r[k]=S[k];});}
  cb(r);},
 set:function(o,cb){Object.keys(o).forEach(function(k){S[k]=o[k];});if(cb)cb();},
 remove:function(keys,cb){(Array.isArray(keys)?keys:[keys]).forEach(function(k){delete S[k];});if(cb)cb();}
}}};
global.window={AIMirrorDialog:{methods:{}},addEventListener:function(){},parent:{postMessage:function(){}}};
global.window.chrome=global.chrome;
global.Vue={h:function(t,p,c){if(p!==undefined&&(typeof p!=='object'||p===null||Array.isArray(p))&&c===undefined){c=p;p={};}return{tag:t,props:p||{},children:c};}};
require(P('08h_profile_fields.js'));
require(P('08g_site_profiles.js'));
require(P('08i_config_cache.js'));
require(P('08j_config_actions.js'));
const D=global.window.AIMirrorDialog;
const GK='aiMirrorConfigCache_global';
function backend(){return{
 profiles:{glm:{label:'glm',hosts:['chatglm.cn','chatglm.com']},
   yuanbao:{label:'腾讯元宝',hosts:['yuanbao.tencent.com']}},
 tool_config:{},system_config:[],flask:{port:5000}};}
function mk(){return{siteKey:'yuanbao.tencent.com',configCache:null,configBackend:null,
 siteProfiles:{},siteProfDraft:{},toolConfig:{},systemConfig:{},_siteProfLoaded:false,
 recomputeConfigDiff:function(){this._n=(this._n||0)+1;},
 resetSiteProfDraft:function(){this._d=(this._d||0)+1;}};}
test('全局单键：空 siteKey 写入，真实域名读回同一份副本',async function(){
 await D.configCacheSet('',{marker:'A'});
 var v=await D.configCacheGet('yuanbao.tencent.com');
 assert.ok(v&&v.marker==='A');assert.ok(!S[GK],'前端零持久化：不再写入 chrome.storage');
});
test('刷新不丢：本地改动与档案刷新后仍在',async function(){
 await D.configCacheSet('',{profiles:{yuanbao:{label:'腾讯元宝'}},pending:[{block:'bridge',body:{x:1}}]});
 var v=await D.configCacheGet('yuanbao.tencent.com');
 assert.ok(v.profiles.yuanbao);assert.strictEqual(v.pending.length,1);
});
test('旧分桶快照自愈：并入新增档案、hosts 乱码归数组、pending 不丢、旧桶清理',async function(){
 await D.configCacheSet('',{profiles:{glm:{label:'glm',hosts:JSON.stringify({0:'chatglm.cn',1:'chatglm.com'})}},
   pending:[{block:'bridge',body:{x:1}}]});
 S['aiMirrorConfigCache_unknown-site']={profiles:{glm:{}}};
 var c=mk();await D.methods.configLoadAndDiff.call(c,backend());
 assert.ok(c.configCache.profiles.yuanbao,'后端新增 yuanbao 未并入');
 assert.deepStrictEqual(c.configCache.profiles.glm.hosts,['chatglm.cn','chatglm.com']);
 assert.strictEqual(c.configCache.pending.length,1,'本地改动被母版覆盖');
 assert.ok(c.siteProfiles.yuanbao);
 assert.ok(!S['aiMirrorConfigCache_unknown-site'],'旧分站点桶未清理');
 assert.strictEqual(D.methods.currentProfileId.call(c),'yuanbao','仍回落 glm');
});
test('再刷新一次：档案与改动仍在',async function(){
 var c=mk();await D.methods.configLoadAndDiff.call(c,backend());
 assert.ok(c.configCache.profiles.yuanbao);
 assert.strictEqual(c.configCache.pending.length,1);
});
test('源码审计：全局键 / 清桶 / 并入函数 / 08j 调用',function(){
 var i=fs.readFileSync(P('08i_config_cache.js'),'utf8');
 assert.ok(i.indexOf('const GLOBAL_KEY')>=0);
 assert.ok(i.indexOf('D.configCachePurgeLegacy')>=0);
 assert.ok(i.indexOf('D.mergeBackendProfiles')>=0);
 var j=fs.readFileSync(P('08j_config_actions.js'),'utf8');
 assert.ok(j.indexOf('configCachePurgeLegacy()')>=0);
 assert.ok(j.indexOf('mergeBackendProfiles(cache, backend)')>=0);
});
test('行数门禁：08i / 08j / 08f 均不超过 450 行',function(){
 ['08i_config_cache.js','08j_config_actions.js','08f_commands.js'].forEach(function(f){
  var n=fs.readFileSync(P(f),'utf8').split(String.fromCharCode(10)).length;
  assert.ok(n<=450,f+' 行数 '+n);});
});
