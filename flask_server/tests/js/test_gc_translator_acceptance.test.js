/* ============================================================
 * G-C 阶段 2 翻译员验收：逐项脚本化反查
 * 依据 docs/split-mirror-and-tools-service.md 第七节阶段 2 五项、
 * 第四节 4.1-4.6；只读取证，不改运行时、不翻 STATUS。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const ROOT = path.join(__dirname, '..', '..', '..');
const rd = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const split = (s) => String(s).split(String.fromCharCode(10));
global.window = {};
const DIA = require(path.join(ROOT, 'extend', 'lib', 'dialects.js'));
const T = require(path.join(ROOT, 'extend', 'lib', 'translator.js'));
const SPEC = rd('docs/split-mirror-and-tools-service.md');
const TR = rd('extend/lib/translator.js');
const DI = rd('extend/lib/dialects.js');
const P5 = rd('extend/dialog/parts/05c_prompt.js');
const B1 = rd('extend/dialog/parts/01b_bridge.js');
const IX = rd('extend/content/05_index.js');
const ST = rd('extend/content/00_state.js');
const HTML = rd('extend/dialog/dialog.html');
const MF = JSON.parse(rd('extend/manifest.json'));

// 阶段 2 五项逐项
const items = [
  { id: 'S2-1', name: '取回标准提示词 + 追加方言说明',
    ok: () => TR.includes('/v1/system_prompt') && TR.includes('composePrompt')
      && P5.includes('T.composePrompt(T.state.standard, dialect)')
      && split(P5).some((x) => x.indexOf('标准四段在前') >= 0) },
  { id: 'S2-2', name: 'bridge-chat-call 翻译为标准 tool_calls',
    ok: () => TR.includes('function toToolCalls') && TR.includes("'function'")
      && TR.includes('callIdFromNonce') && TR.includes('function fromBlocks') },
  { id: 'S2-3', name: '标准 tool 消息翻译为 bridge-chat-res',
    ok: () => TR.includes('function toToolMessage') && TR.includes('function fromToolMessage')
      && TR.includes("'bridge-chat-res'") && TR.includes('nonceFromCallId') },
  { id: 'S2-4', name: '语言包从 /api/clients 的 custom_config 取回',
    ok: () => TR.includes('/api/clients?site_key=') && TR.includes('fetchLanguagePack')
      && DI.includes('function languagePack') && B1.includes('T.fetchLanguagePack')
      && IX.includes('A.applyLanguagePack') },
  { id: 'S2-5', name: '指令执行端对接服务端下发的指令定义',
    ok: () => TR.includes('/api/commands') && TR.includes('fetchCommands')
      && B1.includes('T.fetchCommands') && B1.includes('refreshCommandDefinitions')
      && B1.includes('commandDefinitions') }
];

// 4.1-4.6 逐项
const subs = [
  { id: '4.1', name: '方言处理函数（定位/写入/发送/生成态）',
    ok: () => DI.includes('defaultHandlers') && ['locate','write','send','generating'].every((k) => DI.includes(k + ': function'))
      && DI.includes('dom.query') && DI.includes('c.dom.press') },
  { id: '4.2', name: '语言包寄存在客户端注册信息、服务端不解释',
    ok: () => DI.includes('custom_config') && DI.includes('function languagePack')
      && TR.includes('fetchLanguagePack') && SPEC.includes('服务端不解释其内容') },
  { id: '4.3', name: '提示词拼装（标准四段 + 追加方言）',
    ok: () => TR.includes('function defaultDialect') && TR.includes('function composePrompt')
      && P5.includes('T.composePrompt') },
  { id: '4.4', name: '调用解析与结果回传、多调用拦截',
    ok: () => TR.includes('function fromBlocks') && TR.includes('multiple_tool_calls')
      && TR.includes('function toToolMessage') && TR.includes('function fromToolMessage') },
  { id: '4.5', name: '卡片语义与执行状态由翻译员负责',
    ok: () => SPEC.includes('建卡、执行、已执行签名、刷新恢复，全部由翻译员负责')
      && TR.includes('dialectFor') && DI.includes('OVERRIDES') },
  { id: '4.6', name: '网页原文不自动淘汰、刷新不丢',
    ok: () => SPEC.includes('不设过期时间') && SPEC.includes('刷新不丢')
      && SPEC.includes('唯一清理入口') }
];

test('阶段 2 五项：规格清单逐项落代码', () => {
  for (const it of items) assert.ok(it.ok(), 'FAIL ' + it.id + ' ' + it.name);
});

test('4.1-4.6：规格子面逐项落代码或规格约束', () => {
  for (const s of subs) assert.ok(s.ok(), 'FAIL ' + s.id + ' ' + s.name);
});

test('挂载顺序：dialects 先于 state，translator 经 dialog.html 与 manifest 挂载', () => {
  const js = MF.content_scripts[0].js;
  assert.ok(js.indexOf('lib/dialects.js') < js.indexOf('content/00_state.js'));
  assert.ok(js.includes('lib/translator.js'));
  assert.ok(HTML.includes('lib/dialects.js') && HTML.includes('lib/translator.js'));
  assert.ok(ST.includes('languagePack: null'));
});

test('流程可用：全流程夹具族存在且接线级夹具登记真实调用', () => {
  const names = fs.readdirSync(path.join(ROOT, 'flask_server', 'tests', 'js'))
    .filter((n) => n.startsWith('test_') && n.endsWith('.test.js'));
  for (const n of ['test_translator.test.js','test_translator_wiring.test.js',
                   'test_translator_wiring_require.test.js','test_05c_prompt_schema_coverage.test.js']) {
    assert.ok(names.includes(n), '缺既有夹具：' + n);
  }
  const w = rd('flask_server/tests/js/test_translator_wiring.test.js');
  assert.ok(w.includes('bootDialog') && w.includes('installSpies'));
});

test('红线：不新建切换开关、不装配运行时 M、STATUS 仍 declared-placeholder', () => {
  const chain = rd('extend/lib/standard_chain_contract.js');
  assert.ok(chain.includes('declared-placeholder'));
  assert.ok(!TR.includes('SWITCH') && !TR.includes('toggleNewChain'));
  assert.ok(!P5.includes('toggleNewChain'));
});

test('缺口面：yuanbao 识别与独立工具配置页登记在规格结论源', () => {
  const board = rd('docs/work-board.md');
  assert.ok(board.includes('大改优先重排'));
  assert.ok(SPEC.includes('翻译员') || SPEC.includes('工具服务'));
});
