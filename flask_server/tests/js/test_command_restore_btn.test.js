// 模块：指令编辑态还原按钮的回归测试
const test=require('node:test');const assert=require('node:assert');
const fs=require('node:fs');const path=require('node:path');
const P=(f)=>path.join(__dirname,'..','..','..','extend','dialog','parts',f);
global.Vue={h:(tag,props,children)=>{if(props!==undefined&&(typeof props!=='object'||props===null||Array.isArray(props))&&children===undefined){children=props;props={};}return{tag,props:props||{},children};}};
global.window={AIMirrorDialog:{}};
require(P('08f_commands.js'));const D=global.window.AIMirrorDialog;
function find(n,cls,out){if(!n||typeof n!=='object')return out;if(Array.isArray(n)){n.forEach(x=>find(x,cls,out));return out;}
 const c=n.props&&n.props.class;if(typeof c==='string'&&c.split(/\s+/).indexOf(cls)>=0)out.push(n);
 if(n.children)find(n.children,cls,out);return out;}
function mk(idx){return {
 cmdOpen:true,bridgeEditIdx:idx,
 bridgeCommands:[{name:'/new',label:'开启新对话',selector:'@profile.newConversation'}],
 bridgeNewCmdName:'/new',bridgeNewCmdLabel:'开启新对话 1',bridgeNewCmdIsCombo:false,
 bridgeNewCmdSteps:'',bridgeNewCmdInterval:'1',
 bridgePicked:{selector:'@profile.newConversation',page_url:'',tag:''},
 bridgeCmdParams:{},bridgeCmdParamDefs:[],bridgeHelpGroups:[],
 configCache:{blockFields:{commands:{f1:{baseline:'a',current:'b'}}}},_calls:[],
 toast(){},runBridgeCommand(){},testMdSelector(){},saveBridgeCommand(){},
 startPickElement(){},stopPickElement(){},
 cancelEditBridgeCommand(){this.bridgeEditIdx=null;this._calls.push('cancel');},
 editBridgeCommand(i){this.bridgeEditIdx=i;this._calls.push('reload:'+i);},
 recomputeConfigDiff(){this._calls.push('recalc');},$forceUpdate(){this._calls.push('force');}
};}
test('编辑态：表单旁有纯图标 ↺ 还原按钮',()=>{
 const c=mk(0),v=D.renderCommandBlock(c),b=find(v,'sp-restore-btn',[]);
 assert.strictEqual(b.length,1);assert.strictEqual(b[0].tag,'button');
 assert.strictEqual(typeof b[0].props.onClick,'function');
 assert.ok(b[0].props.title.indexOf('还原')>=0);
 const s=JSON.stringify(b[0]);
 assert.ok(s.indexOf('sp-restore-icon')>=0&&s.indexOf('↺')>=0);
 assert.strictEqual(s.indexOf(' 还原'),-1,'仍带可见文字');});
test('点击还原：整条重新载入、差异清空、徽标重算',()=>{
 const c=mk(0),v=D.renderCommandBlock(c),b=find(v,'sp-restore-btn',[])[0];
 b.props.onClick();assert.ok(c._calls.indexOf('reload:0')>=0);
 assert.strictEqual(c.bridgeEditIdx,0);
 assert.ok(!c.configCache.blockFields.commands,'commands 差异未清');
 assert.ok(c._calls.indexOf('recalc')>=0);});
test('新建态：不显示还原按钮（无母本可还原）',()=>{
 const c=mk(null),v=D.renderCommandBlock(c);
 assert.strictEqual(find(v,'sp-restore-btn',[]).length,0);});
test('源码审计：08f 含 restoreCmdEdit 且不含可见「 还原」文字',()=>{
 const s=fs.readFileSync(P('08f_commands.js'),'utf8');
 assert.ok(s.indexOf('function restoreCmdEdit')>=0);
 assert.strictEqual(s.indexOf("' 还原'"),-1);});
test('行数门禁：08f 不超过 450 行',()=>{
 const n=fs.readFileSync(P('08f_commands.js'),'utf8').split(String.fromCharCode(10)).length;
 assert.ok(n<=450,'08f 行数 '+n);});
