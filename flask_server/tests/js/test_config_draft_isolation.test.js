// 模块：C-10 按站草稿 + 改完即生效 + 无中间态
const test=require('node:test');const assert=require('node:assert');
const fs=require('node:fs');const path=require('node:path');
const P=(f)=>path.join(__dirname,'..','..','..','extend','dialog','parts',f);
const R=(f)=>path.join(__dirname,'..','..','..',f);
const calls=[];
global.window={AIMirrorDialog:{methods:{}},addEventListener:()=>{},parent:{postMessage:()=>{}}};
global.Vue={h:(t,p,c)=>({tag:t,props:p||{},children:c})};
global.fetch=function(u,o){calls.push({url:u,headers:(o&&o.headers)||{}});return Promise.resolve({ok:true,json:()=>Promise.resolve({success:true})});};
require(P('08h_profile_fields.js'));
require(P('08g_site_profiles.js'));
require(P('08i_config_cache.js'));
require(P('00a_api.js'));
const D=global.window.AIMirrorDialog;
D.serializeProfilesDraft=function(d){return d;};
test('草稿按站隔离：A 站写入，B 站读不到',async()=>{
 await D.configCacheSet('a.com',{marker:'A'});
 assert.strictEqual((await D.configCacheGet('a.com')).marker,'A');
 assert.strictEqual(await D.configCacheGet('b.com'),null);
});
test('所有请求带 X-Site-Key，后端据此取该站草稿',async()=>{
 calls.length=0;
 const ctx={siteKey:'yuanbao.tencent.com',config:{flaskUrl:'http://127.0.0.1:5000'}};
 await D.apiFetch(ctx,'/config/draft',{});
 assert.strictEqual(calls[0].headers['X-Site-Key'],'yuanbao.tencent.com');
});
test('源码审计：后端按站分文件 + 即时生效；前端不再排队',()=>{
 const st=fs.readFileSync(R('flask_server/config_draft_store.py'),'utf8');
 assert.ok(st.indexOf('def _path(site)')>=0);
 assert.ok(st.indexOf('def apply_to_runtime')>=0);
 const cr=fs.readFileSync(R('flask_server/routes/config_route.py'),'utf8');
 assert.ok(cr.indexOf('draft_store.load(site)')>=0);
 assert.ok(cr.indexOf('X-Site-Key')>=0);
 const dir=P('');let all='';
 fs.readdirSync(dir).filter(f=>f.endsWith('.js')).forEach(f=>{all+=fs.readFileSync(path.join(dir,f),'utf8');});
 assert.ok(all.indexOf('cache.pending = []')>=0,'仍登记 pending 队列');
});

// ---- C-10 拦截层口径（从 test_config_blocks 迁入） ----
require(P('08k_config_blocks.js'));
require(P('08j_config_actions.js'));
test('C-10 配置写：不排队，写该站草稿并即时发原端点生效', async()=>{
 calls.length=0;
 const ctx={siteKey:'a.com',config:{flaskUrl:'http://127.0.0.1:5000'},configCache:{},configDraftMode:true};
 D._cfgCtx=ctx;
 const r=await D.apiFetch(ctx,'/api/bridge/config',{method:'POST',body:{app_id:'x'}});
 assert.strictEqual(r.draft,true);
 assert.deepStrictEqual(ctx.configCache.pending,[],'仍登记 pending 中间态');
 assert.strictEqual(ctx.configCache.app_id,'x');
 const urls=calls.map(c=>c.url);
 assert.ok(urls.some(u=>u.indexOf('/config/draft')>=0),'未写该站后端草稿');
 assert.ok(!urls.some(u=>u.indexOf('/api/bridge/config')>=0),'草稿态不应写原端点/母版');
 assert.ok(calls.every(c=>c.headers['X-Site-Key']==='a.com'),'请求缺 X-Site-Key');
});
test('C-10 源码：queuePendingWrite 清空 pending 且不再去重排队',()=>{
 const src=fs.readFileSync(P('08j_config_actions.js'),'utf8');
 assert.ok(src.indexOf('cache.pending = []')>=0);
 assert.ok(src.indexOf('pushPending')<0||src.indexOf('queuePendingWrite')>=0);
});
