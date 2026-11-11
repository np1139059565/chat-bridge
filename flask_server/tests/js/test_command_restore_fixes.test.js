// 模块：指令区还原按钮与差异同步的回归测试
const test=require('node:test');const assert=require('node:assert');
const fs=require('node:fs');const path=require('node:path');
const P=(f)=>path.join(__dirname,'..','..','..','extend','dialog','parts',f);
const R=(f)=>path.join(__dirname,'..','..','..',f);
global.Vue={h:(t,p,c)=>{if(p!==undefined&&(typeof p!=='object'||p===null||Array.isArray(p))&&c===undefined){c=p;p={};}return{tag:t,props:p||{},children:c};}};
global.window={AIMirrorDialog:{}};
require(P('08f_commands.js'));const D=global.window.AIMirrorDialog;
function find(n,cls,out){if(!n||typeof n!=='object')return out;if(Array.isArray(n)){n.forEach(x=>find(x,cls,out));return out;}
 const c=n.props&&n.props.class;if(typeof c==='string'&&c.split(/\s+/).indexOf(cls)>=0)out.push(n);
 if(n.children)find(n.children,cls,out);return out;}
function mk(idx,dirty,builtin){const bb={};if(dirty)bb.f3={baseline:'a',current:'b'};
 if(builtin)bb['cmdparam.md.selector']={baseline:'.old',current:'.new'};return{
 cmdOpen:true,bridgeEditIdx:idx,
 bridgeCommands:[{name:'/new',label:'开启新对话',selector:'@profile.newConversation'}],
 bridgeNewCmdName:'/new',bridgeNewCmdLabel:'开启新对话',bridgeNewCmdIsCombo:false,
 bridgeNewCmdSteps:'',bridgeNewCmdInterval:'1',bridgePicked:{selector:'@profile.newConversation'},
 bridgeCmdParams:{md:{selector:'.new'}},
 bridgeCmdParamDefs:[{cmd:'md',key:'selector',label:'Markdown 复制按钮选择器',hint:'留空则关闭'}],
 bridgeHelpGroups:[],configCache:{blockFields:{commands:bb}},_calls:[],
 toast(){},runBridgeCommand(){},testMdSelector(){},saveBridgeCommand(){},
 startPickElement(){},stopPickElement(){},
 cancelEditBridgeCommand(){this.bridgeEditIdx=null;this._calls.push('cancel');},
 editBridgeCommand(i){this.bridgeEditIdx=i;this._calls.push('reload:'+i);},
 recomputeConfigDiff(){this._calls.push('recalc');},$forceUpdate(){this._calls.push('force');}};}
test('无差异：编辑态不显示 ↺（手动改回后按钮与徽标消失）',()=>{
 assert.strictEqual(find(D.renderCommandBlock(mk(0,false,false)),'sp-restore-btn',[]).length,0);});
test('有差异：编辑态纯图标 ↺，点击清差异',()=>{
 const c=mk(0,true,false),b=find(D.renderCommandBlock(c),'sp-restore-btn',[]);
 assert.strictEqual(b.length,1);assert.ok(b[0].props.title.indexOf('还原')>=0);
 assert.ok(JSON.stringify(b[0]).indexOf('↺')>=0);
 assert.strictEqual(JSON.stringify(b[0]).indexOf(' 还原'),-1);
 b[0].props.onClick();assert.ok(c._calls.indexOf('recalc')>=0);});
test('参数：稳定 key + 有差异才出 ↺，点击恢复母本',()=>{
 const c=mk(null,false,true),v=D.renderCommandBlock(c),b=find(v,'sp-restore-btn',[]);
 assert.strictEqual(b.length,1,'参数旁缺还原按钮');
 const inp=[];function fi(n){if(!n||typeof n!=='object')return;if(Array.isArray(n)){n.forEach(fi);return;}
 if(n.props&&n.props['data-cfg-key'])inp.push(n.props['data-cfg-key']);if(n.children)fi(n.children);}fi(v);
 assert.ok(inp.indexOf('cmdparam.md.selector')>=0,'缺稳定 key');
 b[0].props.onClick();assert.strictEqual(c.bridgeCmdParams.md.selector,'.old');
 assert.ok(!c.configCache.blockFields.commands['cmdparam.md.selector']);});
test('源码：08l baseline 幂等、相等即清；08f 无可见文字',()=>{
 const l=fs.readFileSync(P('08l_config_field_tracking.js'),'utf8');
 assert.ok(l.indexOf('if (BASE.has(el)) return;')>=0);
 assert.ok(l.indexOf('delete bb[key]')>=0);
 const f=fs.readFileSync(P('08f_commands.js'),'utf8');
 assert.ok(f.indexOf('cmdDirty(ctx')>=0);assert.ok(f.indexOf('restoreCmdParam')>=0);
 assert.strictEqual(f.indexOf("' 还原'"),-1);});
test('CSS：徽标让位折叠按钮，参数行同行图标',()=>{
 const c=fs.readFileSync(R('extend/dialog/styles/02f_site_profiles.css'),'utf8');
 assert.ok(c.indexOf('right: 56px')>=0);
 assert.ok(c.indexOf('.sp-block-wrap .card-head button')>=0);
 assert.ok(c.indexOf('max-width: calc(100% - 130px)')>=0);
 assert.ok(c.indexOf('.bridge-builtin-params label')>=0);});
test('行数门禁：08f / 08l 均不超过 450 行',()=>{
 ['08f_commands.js','08l_config_field_tracking.js'].forEach(f=>{
 const n=fs.readFileSync(P(f),'utf8').split(String.fromCharCode(10)).length;
 assert.ok(n<=450,f+' 行数 '+n);});});
