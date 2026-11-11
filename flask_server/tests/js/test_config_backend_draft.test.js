// 模块：配置副本后端化的回归测试
const test=require('node:test');const assert=require('node:assert');
const fs=require('node:fs');const path=require('node:path');
const P=(f)=>path.join(__dirname,'..','..','..','extend','dialog','parts',f);
const R=(f)=>path.join(__dirname,'..','..','..',f);
const calls=[];
global.window={AIMirrorDialog:{methods:{}},addEventListener:function(){},parent:{postMessage:function(){}}};
global.Vue={h:function(t,p,c){if(p!==undefined&&(typeof p!=='object'||p===null||Array.isArray(p))&&c===undefined){c=p;p={};}return{tag:t,props:p||{},children:c};}};
require(P('08h_profile_fields.js'));
require(P('08g_site_profiles.js'));
require(P('08i_config_cache.js'));
require(P('08j_config_actions.js'));
const D=global.window.AIMirrorDialog;
D.apiFetch=function(ctx,p,o){calls.push({path:p,body:o&&o.body,commit:o&&o.__commit});return Promise.resolve({success:true});};
D.serializeProfilesDraft=function(d){return d;};
function backend(){return{master:{profiles:{glm:{label:'glm',hosts:['chatglm.cn']},yuanbao:{label:'元宝',hosts:['yuanbao.tencent.com']}},tools:{},tool_config:{},system_config:[],limits:{max_json_chars:200},flask:{port:5000}},draft:null};}
function mk(){return{siteKey:'yuanbao.tencent.com',configCache:null,configBackend:null,
 siteProfiles:{},siteProfDraft:{},toolConfig:{},systemConfig:{},maxJsonChars:200,configTools:{},
 _siteProfLoaded:false,recomputeConfigDiff:function(){this._n=(this._n||0)+1;},
 resetSiteProfDraft:function(){this._d=(this._d||0)+1;}};}
test('刷新回两份：configBackend=master，configCache=draft',async function(){
 const b=backend();b.draft=Object.assign({},b.master,{limits:{max_json_chars:201},pending:[{block:'bridge'}]});
 const c=mk();await D.methods.configLoadAndDiff.call(c,b);
 assert.strictEqual(c.configBackend,b.master);
 assert.strictEqual(c.configCache.limits.max_json_chars,201);
 assert.strictEqual(c.configCache.pending.length,1);
 assert.strictEqual(c.maxJsonChars,200);
});
test('无草稿时以 master 初始化，且不串站点',async function(){
 const c=mk();await D.methods.configLoadAndDiff.call(c,backend());
 assert.ok(c.configCache.profiles.yuanbao);
 assert.strictEqual(D.methods.currentProfileId.call(c),'yuanbao');
});
test('界面改动立即写后端缓存文件：/config/draft + __commit',async function(){
 calls.length=0;const c=mk();await D.methods.configLoadAndDiff.call(c,backend());
 c.maxJsonChars=201;c.toolConfig={read_file:{x:1}};
 D.configCacheSet(c.siteKey,c.configCache);
 await new Promise(function(r){setTimeout(r,220);});
 const hit=calls.filter(function(x){return x.path==='/config/draft';});
 assert.strictEqual(hit.length,1,'未写后端草稿');
 assert.strictEqual(hit[0].commit,true);
 assert.strictEqual(hit[0].body.limits.max_json_chars,201);
 assert.deepStrictEqual(hit[0].body.tool_config,{read_file:{x:1}});
});
test('源码审计：前端无 chrome 持久化、刷新走 /config/draft、覆盖走 /config/commit',function(){
 const i=fs.readFileSync(P('08i_config_cache.js'),'utf8');
 assert.ok(i.indexOf("D.configDraftSave")>=0);
 assert.ok(i.indexOf("'/config/draft'")>=0);
 assert.ok(i.indexOf('chrome.storage.local')<0 || i.indexOf('const s = localStore();\n    if (!s) return Promise.resolve(MEM[key] || null)')<0);
 const b=fs.readFileSync(P('01_backend.js'),'utf8');
 assert.ok(b.indexOf("'/config/draft'")>=0);
 const j=fs.readFileSync(P('08j_config_actions.js'),'utf8');
 assert.ok(j.indexOf("'/config/commit'")>=0);
});
test('行数门禁：08i / 08j 不超过 450 行',function(){
 ['08i_config_cache.js','08j_config_actions.js'].forEach(function(f){
  const n=fs.readFileSync(P(f),'utf8').split(String.fromCharCode(10)).length;
  assert.ok(n<=450,f+' 行数 '+n);});
});
