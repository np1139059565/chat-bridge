/* ============================================================
 * 孤儿切片兜底行为测试
 *
 * 背景：
 *   网页切片与已建消息树「断裂」时（找不到任何可衔接的边），整片不入树，
 *   转而存在 orphanSlice 里仅供展示。此时 branchKeys 为空，若导出/渲染
 *   只看 branchKeys，就会出现「镜像区有内容、列表却为空」「导出空结构」
 *   这类自相矛盾的现象。
 *
 *   兜底规则：timeline 为空且 orphanSlice 非空时，改用 orphanSlice 组装。
 *   本文件覆盖这条兜底在「导出」路径上的两种情形：
 *     - orphanSlice 为空：导出结果的消息列表为空
 *     - orphanSlice 非空：消息按切片顺序导出，key 为 orphan-N
 *
 * 运行：node --test flask_server/tests/js/*.test.js
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// ---- 全局桩：必须在加载被测模块之前就位（公共部分见 _part_stub）----
const dialog = require('./_part_stub').installStub();
// 本测试特有的桩：buildTimeline 固定为空，才能走到孤儿切片兜底分支
dialog.buildTimeline = () => [];
// 外部卡片在导出里用不到，给个确定性实现即可
dialog.externalCardKey = (c) => 'ext-' + (c && c.id);

// 引入真实的公共工具库：msgId → messageFingerprint → 公共库，这条链跨三个文件。
// 直接用生产实现，不自己造假货，测的才是线上真正跑的代码。
require(path.join(__dirname, '..', '..', '..', 'extend', 'lib', 'dom-utils.js'));
// 消息指纹挂在 04_sessions 上（转调公共库），msgId 在 05f 里转调它
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '04_sessions.js'));
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '05f_parse.js'));
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '05c_prompt.js'));

const M = dialog.methods;

/**
 * 造一条最小消息节点。
 *
 * @param {string} id 消息 id（参与指纹计算）
 * @param {string} text 正文
 * @returns {Object} 消息节点
 */
function makeNode(id, text) {
  return {
    id: id,
    role: 'user',
    name: '用户',
    blocks: [{ type: 'paragraph', text: text }],
    cards: {}
  };
}

/**
 * 造一个会话对象。
 *
 * @param {Array} orphanSlice 孤儿切片
 * @returns {Object} 会话
 */
function makeConv(orphanSlice) {
  return {
    title: 't',
    page_url: 'http://x',
    msgTree: {},
    visibleKeys: [],
    branchKeys: [],
    externalCards: [],
    orphanSlice: orphanSlice || []
  };
}

test('orphanSlice 为空时，导出消息列表为空', () => {
  const conv = makeConv([]);
  const out = M.buildConvExport.call(M, 'c1', conv, null, 'history');
  assert.strictEqual(out.messageCount, 0);
  assert.deepStrictEqual(out.messages, []);
});

test('orphanSlice 非空时，消息按切片顺序导出', () => {
  const conv = makeConv([makeNode('m1', '第一条'), makeNode('m2', '第二条')]);
  const out = M.buildConvExport.call(M, 'c1', conv, null, 'history');
  assert.strictEqual(out.messages.length, 2);
  // 顺序必须与切片一致，否则导出的对话会前后颠倒
  assert.strictEqual(out.messages[0].blocks[0].text, '第一条');
  assert.strictEqual(out.messages[1].blocks[0].text, '第二条');
});

test('orphanSlice 兜底时仍带出会话元信息', () => {
  const conv = makeConv([makeNode('m1', '内容')]);
  const out = M.buildConvExport.call(M, 'c9', conv, null, 'visible');
  assert.strictEqual(out.conversationId, 'c9');
  assert.strictEqual(out.title, 't');
  assert.strictEqual(out.page_url, 'http://x');
  assert.strictEqual(out.source, 'ai-mirror');
});

test('可见区来源与历史来源在兜底时结果一致', () => {
  const conv = makeConv([makeNode('m1', '只有一条')]);
  const a = M.buildConvExport.call(M, 'c1', conv, null, 'history');
  const b = M.buildConvExport.call(M, 'c1', conv, null, 'visible');
  // 两者 branchKeys / visibleKeys 都是空，都应落到 orphanSlice 兜底
  assert.strictEqual(a.messageCount, b.messageCount);
  assert.strictEqual(a.messages[0].blocks[0].text, b.messages[0].blocks[0].text);
});
