// 模块：配置草稿按 siteKey 隔离（C-10 重写，推翻 C-8 全局单键）
const test=require('node:test');const assert=require('node:assert');
const fs=require('node:fs');const path=require('node:path');
const P=(f)=>path.join(__dirname,'..','..','..','extend','dialog','parts',f);
global.chrome={storage:{local:{get:(k,cb)=>cb({}),set:(o,cb)=>cb&&cb(),remove:(k,cb)=>cb&&cb()}}};
global.window={AIMirrorDialog:{methods:{}},addEventListener:()=>{},parent:{postMessage:()=>{}}};
global.window.chrome=global.chrome;
global.Vue={h:(t,p,c)=>({tag:t,props:p||{},children:c})};
require(P('08h_profile_fields.js'));
require(P('08g_site_profiles.js'));
require(P('08i_config_cache.js'));
require(P('08j_config_actions.js'));
const D=global.window.AIMirrorDialog;
D.serializeProfilesDraft=function(d){return d;};
function backend(){return{profiles:{glm:{label:'glm',hosts:['chatglm.cn']},yuanbao:{label:'元宝',hosts:['yuanbao.tencent.com']}},tools:{},tool_config:{},system_config:[],flask:{port:5000}};}
function mk(){return{siteKey:'yuanbao.tencent.com',configCache:null,configBackend:null,siteProfiles:{},siteProfDraft:{},toolConfig:{},systemConfig:{},_siteProfLoaded:false,recomputeConfigDiff(){},resetSiteProfDraft(){}};}
test('按站隔离：A 站写入，B 站读不到',async()=>{
 await D.configCacheSet('a.com',{marker:'A'});
 assert.strictEqual((await D.configCacheGet('a.com')).marker,'A');
 assert.strictEqual(await D.configCacheGet('b.com'),null);
});
test('无后端草稿时以 master 初始化，站点档案不串 glm',async()=>{
 const c=mk();await D.methods.configLoadAndDiff.call(c,backend());
 assert.ok(c.configCache.profiles.yuanbao);
 assert.strictEqual(D.methods.currentProfileId.call(c),'yuanbao');
});
test('后端草稿优先于内存副本，master 仍唯一',async()=>{
 const b={master:backend(),draft:Object.assign({},backend(),{limits:{max_json_chars:201},pending:[{block:'bridge'}]})};
 const c=mk();await D.methods.configLoadAndDiff.call(c,b);
 assert.strictEqual(c.configBackend,b.master);
 assert.strictEqual(c.configCache.limits.max_json_chars,201);
});
test('源码审计：后端草稿模块存在、08j 仍并入后端新增档案',()=>{
 assert.ok(fs.existsSync(path.join(__dirname,'..','..','..','flask_server','config_draft_store.py')));
 const j=fs.readFileSync(P('08j_config_actions.js'),'utf8');
 assert.ok(j.indexOf('mergeBackendProfiles(cache, backend)')>=0);
});
test('行数门禁：08i / 08j 不超过 450 行',()=>{
 ['08i_config_cache.js','08j_config_actions.js'].forEach(f=>{
  const n=fs.readFileSync(P(f),'utf8').split(String.fromCharCode(10)).length;
  assert.ok(n<=450,f+' 行数 '+n);});
});
