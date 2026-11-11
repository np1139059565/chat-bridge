// 模块：C-7 指令区统一列表 + 行内编辑
const test=require('node:test');const assert=require('node:assert');
const fs=require('node:fs');const path=require('node:path');
const P=(f)=>path.join(__dirname,'..','..','..','extend','dialog','parts',f);
const R=(f)=>path.join(__dirname,'..','..','..',f);
global.Vue={h:(t,p,c)=>{if(p!==undefined&&(typeof p!=='object'||p===null||Array.isArray(p))&&c===undefined){c=p;p={};}return{tag:t,props:p||{},children:c};}};
global.window={AIMirrorDialog:{methods:{}},addEventListener:()=>{},parent:{postMessage:()=>{}}};
require(P('08f_commands.js'));
require(P('01c_bridge_cmd.js'));
const D=global.window.AIMirrorDialog;
D.configCacheSet=()=>Promise.resolve(true);
D.apiFetch=()=>{throw new Error('内置编辑不应发请求');};
function find(n,cls,out){if(!n||typeof n!=='object')return out;if(Array.isArray(n)){n.forEach(x=>find(x,cls,out));return out;}
 const c=n.props&&n.props.class;if(typeof c==='string'&&c.split(/\s+/).indexOf(cls)>=0)out.push(n);
 if(n.children)find(n.children,cls,out);return out;}
function txt(n){return JSON.stringify(n);}
function mk(over){return Object.assign({
 cmdOpen:true,bridgeEditIdx:null,bridgeCmdFormOpen:false,_cmdEditBuiltin:null,
 bridgeCommands:[{name:'/x',label:'自定义X',selector:'.x'}],
 bridgeHelpGroups:[{group:'采集',items:[{key:'/md',name:'/md',desc:'采集 Markdown'}]}],
 bridgeCmdParamDefs:[],bridgeCmdParams:{},bridgePicked:null,
 bridgeNewCmdName:'',bridgeNewCmdLabel:'',bridgeNewCmdDesc:'',bridgeNewCmdIsCombo:false,
 bridgeNewCmdSteps:'',bridgeNewCmdInterval:'1',siteKey:'a.com',
 configCache:{blockFields:{}},_ran:[],
 runBridgeCommand(k){this._ran.push(k);},
 editBridgeCommand(i){this.bridgeEditIdx=i;this._cmdEditBuiltin=null;},
 cancelEditBridgeCommand(){this.bridgeEditIdx=null;this.bridgeCmdFormOpen=false;},
   _resetCmdForm(){D.methods._resetCmdForm.call(this);},
 removeBridgeCommand(i){this.bridgeCommands.splice(i,1);},
 saveBridgeCommand(){return D.methods.saveBridgeCommand.call(this);},
 toast(m){this._toast=String(m);},startPickElement(){},testMdSelector(){},
 recomputeConfigDiff(){this._recalc=(this._recalc||0)+1;},$forceUpdate(){this._force=(this._force||0)+1;}
},over||{});}
test('统一列表：内置与自定义同表，独立分组与顶部常驻表单消失',()=>{
 const v=D.renderCommandBlock(mk());const t=txt(v);
 assert.ok(t.indexOf('/md')>=0);assert.ok(t.indexOf('/x')>=0);
 assert.ok(t.indexOf('内置')>=0&&t.indexOf('自定义')>=0);
 assert.strictEqual(t.indexOf('可用指令（点击即执行）'),-1,'内置仍单独成块');
 assert.strictEqual(find(v,'cmd-inline-editor',[]).length,0,'默认不该有编辑器');
});
test('点添加：行内展开编辑器，不再常驻',()=>{
 const c=mk();const add=find(D.renderCommandBlock(c),'cmd-add-btn',[])[0];
 add.props.onClick();
 assert.ok(c.bridgeCmdFormOpen);
 assert.strictEqual(find(D.renderCommandBlock(c),'cmd-inline-editor',[]).length,1);
});
test('点自定义行编辑：编辑器出现在该行内',()=>{
 const c=mk();const v=D.renderCommandBlock(c);
 const edit=find(v,'cmd-row-btn',[]).filter(b=>b.props.title==='编辑')[1];
 edit.props.onClick();
 const v2=D.renderCommandBlock(c);
 assert.strictEqual(c.bridgeEditIdx,0);
 assert.strictEqual(find(v2,'cmd-inline-editor',[]).length,1);
});
test('隐藏内置 / 恢复默认：写入按站草稿且不串',()=>{
 const c=mk();const del=find(D.renderCommandBlock(c),'cmd-row-btn',[]).filter(b=>b.props.title==='隐藏此内置指令')[0];
 del.props.onClick();
 assert.ok(c.configCache.hiddenBuiltins.indexOf('/md')>=0);
 assert.strictEqual(txt(D.renderCommandBlock(c)).indexOf('/md'),-1);
 const back=find(D.renderCommandBlock(c),'cmd-hidden-bar',[])[0];
 const btn=find(back,'cmd-row-btn',[])[0];btn.props.onClick();
 assert.strictEqual(c.configCache.hiddenBuiltins.length,0);
 assert.ok(txt(D.renderCommandBlock(c)).indexOf('/md')>=0);
});
test('内置行编辑保存：只改草稿覆盖，不发后端请求',async()=>{
 const c=mk({_cmdEditBuiltin:'/md',bridgeNewCmdName:'/md',bridgeNewCmdLabel:'采 Markdown',bridgeNewCmdDesc:'新描述'});
 await c.saveBridgeCommand();
 assert.strictEqual(c.configCache.builtinOverrides['/md'].label,'采 Markdown');
 assert.strictEqual(c.configCache.builtinOverrides['/md'].desc,'新描述');
 const v=D.renderCommandBlock(mk({configCache:{blockFields:{},builtinOverrides:c.configCache.builtinOverrides}}));
 assert.ok(txt(v).indexOf('采 Markdown')>=0);
});
test('源码审计：统一列表标志 / 01c 复位 / 行数门禁',()=>{
 const f=fs.readFileSync(P('08f_commands.js'),'utf8');
 assert.ok(f.indexOf('hiddenBuiltins')>=0&&f.indexOf('builtinOverrides')>=0);
 assert.strictEqual(f.indexOf(' 还原'),-1);
 const c=fs.readFileSync(P('01c_bridge_cmd.js'),'utf8');
 assert.ok(c.indexOf('bridgeCmdFormOpen = false')>=0&&c.indexOf('_cmdEditBuiltin')>=0);
 const n=f.split(String.fromCharCode(10)).length;assert.ok(n<=450,'08f 行数 '+n);
});
