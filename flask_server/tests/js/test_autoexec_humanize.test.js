// 回归: 倒计时在设定窗口内随机, 执行时机与显示分离。
// 回归: 实际执行只一次, 不超设定值, 到点才触发。
// 回归: 随机因子可注入, 实际值随 rnd 单调。
// 回归: 随机值写日志, 含设定/实际/因子三要素。
// 回归: 顺延 10~20 秒随机, 到点只重试一次。
// 回归: 频率闸未超限记窗口并立即执行。
// 回归: 频率闸超限顺延后重试执行。
// 回归: 源码审计落点与行数门禁。
// 回归: 显示倒计时与真实执行时机分离。
// 回归: 每分钟上限以窗口计数实现。
// 回归: 随机留痕不污染卡片状态。
// 来源: 2号仓 feat(autoexec), 行为对齐 main 现版。
// 模块：C-② 自动执行拟人化
const test=require('node:test');const assert=require('node:assert');
const fs=require('node:fs');const path=require('node:path');
const P=(f)=>path.join(__dirname,'..','..','..','extend','dialog','parts',f);
global.window={AIMirrorDialog:{log:()=>{},methods:{}},addEventListener:()=>{},parent:{postMessage:()=>{}}};
  
require(P('00b_lifecycle.js'));require(P('05l_autoexec.js'));
const D=global.window.AIMirrorDialog;
  const M=D.methods;
  const logs=[];
  D.log=(m)=>logs.push(String(m));
  
function fakeClock(){
 const o=global.setTimeout,oc=global.clearTimeout;let now=0;const q=[];let id=0;
 global.setTimeout=(fn,ms)=>{q.push({at:now+(ms||0),fn,id:++id});return id;};
 global.clearTimeout=(h)=>{const i=q.findIndex(x=>x.id===h);if(i>=0)q.splice(i,1);};
 return {advance(ms){const end=now+ms;
  for(;
  ;
  ){q.sort((a,b)=>a.at-b.at||a.id-b.id);
  const n=q[0];
  if(!n||n.at>end)break;
  q.shift();
  now=n.at;
  n.fn();
  }now=end;
  },
  restore(){global.setTimeout=o;global.clearTimeout=oc;}};
}
test('实际执行只一次、不超设定值、到点才触发',()=>{
 const c=fakeClock();D.random=()=>0;let done=0;const card={};
 D.startCountdown({autoSendDelay:3000},card,'exec',()=>done++);
 assert.ok(Math.abs(card._cdReal-2.1)<1e-9,'实际值 '+card._cdReal);
  assert.strictEqual(card.countdown,3);
  
 c.advance(2099);assert.strictEqual(done,0,'提前执行');
 c.advance(1);assert.strictEqual(done,1,'到点未执行');
 assert.strictEqual(card.countdown,0);assert.strictEqual(card.phase,'');
 c.advance(6000);assert.strictEqual(done,1,'重复执行');
 delete D.random;c.restore();
});
test('随机因子可注入，实际值随 rnd 单调',()=>{
 const vals=[];
 for(const x of [0,0.5,1]){const c=fakeClock();
  D.random=()=>x;
  const card={};
  D.startCountdown({autoSendDelay:5000},card,'exec',()=>{});
  vals.push(card._cdReal);
  delete D.random;
  c.restore();
  }
 assert.ok(vals[0]<vals[1]&&vals[1]<vals[2]);
 assert.strictEqual(Math.round(vals[0]*100)/100,3.5);
  assert.strictEqual(Math.round(vals[2]*100)/100,5);
  
});
test('随机值记日志，含设定/实际/因子',()=>{
 logs.length=0;
  const c=fakeClock();
  D.random=()=>0.5;
  D.startCountdown({autoSendDelay:3000},{},'exec',()=>{});
  
 assert.ok(logs.some(x=>x.indexOf('[拟人化]')>=0&&x.indexOf('实际=')>=0&&x.indexOf('随机因子=')>=0));
 delete D.random;c.restore();
});
test('顺延 10~20 秒随机，到点只重试一次',()=>{
 const c=fakeClock();D.random=()=>0;let done=0;const card={};
 D.startDeferredCountdown({},card,'exec',()=>done++);
 assert.ok(card.countdown>=10&&card.countdown<=20);assert.strictEqual(card.phase,'exec');
 c.advance(9999);assert.strictEqual(done,0);
 c.advance(1);assert.strictEqual(done,1);
 c.advance(20000);assert.strictEqual(done,1);
 delete D.random;c.restore();
});
test('cancelCountdown 清执行与显示两个定时器',()=>{
 const c=fakeClock();D.random=()=>0.5;let done=0;const card={};
 D.startCountdown({autoSendDelay:3000},card,'exec',()=>done++);
 D.cancelCountdown(card);c.advance(9999);
 assert.strictEqual(done,0);assert.strictEqual(card.countdown,0);
 delete D.random;c.restore();
});
test('频率闸：未超限记窗口并立即执行；超限顺延后重试执行',()=>{
 const orig=D.startDeferredCountdown;
 const ctx={_autoExecWindow:[],configCache:{autoExecLimitEnabled:true,autoExecPerMinute:1},execs:0,
  scheduleExecute(){this.execs++;}};
 ctx._gateAutoExec=M._gateAutoExec.bind(ctx);
 ctx._gateAutoExec({id:1},false);
 assert.strictEqual(ctx.execs,1);assert.strictEqual(ctx._autoExecWindow.length,1);
 D.startDeferredCountdown=function(c,card,ph,cb){ctx._deferred=card.id;ctx._deferCb=cb;};
 ctx._gateAutoExec({id:2},true);
 assert.strictEqual(ctx._deferred,2);ctx._deferCb();
 assert.strictEqual(ctx.execs,2,'顺延后应重试执行');
 D.startDeferredCountdown=orig;
});
test('源码审计：落点 + 行数门禁',()=>{
 const b=fs.readFileSync(P('00b_lifecycle.js'),'utf8');
 assert.ok(b.indexOf('0.7 + 0.3')>=0&&b.indexOf('startDeferredCountdown')>=0&&b.indexOf('_cdDisplay')>=0);
  
 const a=fs.readFileSync(P('05l_autoexec.js'),'utf8');
 assert.ok(a.indexOf('_gateAutoExec')>=0&&a.indexOf('60000')>=0&&a.indexOf('configCache')>=0);
 ['00b_lifecycle.js','05l_autoexec.js','08j_config_actions.js'].forEach(f=>{
  const n=fs.readFileSync(P(f),'utf8').split(String.fromCharCode(10)).length;
  assert.ok(n<=450,f+' 行数 '+n);
  });
  
});
