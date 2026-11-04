/* ============================================================
 * 会话加载失败时的数据保护测试
 *
 * 背景（现场日志）：
 *   memLoadConv 失败: TypeError: Failed to fetch
 *   loadConversation: 后端与本地均无会话
 *   [签名诊断] 查 sig=... 库内条数=0 命中=false
 *   persistConv 写入后端：签名=0
 *
 * 即：后端连不上 → 加载返回 null → 被当成「后端没有这个会话」→
 * 解除写回禁令 → 用内存里的空签名库覆盖后端存档。刷新一次毁一次。
 *
 * 本文件把「加载失败不得当作空会话」这条钉死。
 *
 * 说明：被测模块内部调用全局 D.apiFetch，故每个用例都要重设它，
 * 否则会沿用上一个用例的桩，测出假结果。
 *
 * 运行：node --test flask_server/tests/js/*.test.js
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// ---- 全局桩 ----
const dialog = { methods: {}, log: () => {} };
global.window = { AIMirrorDialog: dialog, AIMirrorDomUtils: { toArray: (v) => (Array.isArray(v) ? v : []) } };

require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '05h_memory_bridge.js'));

const M = dialog.methods;

/**
 * 造一个只够跑加载逻辑的上下文，并把 apiFetch 装到全局 D 上。
 *
 * @param {Function} fetchFn 桩函数
 * @returns {Object} 上下文
 */
function makeCtx(fetchFn) {
  dialog.apiFetch = fetchFn;
  return { siteKey: 's', log: () => {} };
}

test('取会话成功：返回会话对象', async () => {
  const ctx = makeCtx(async () => ({ conv: { title: 't' } }));
  const r = await M.memLoadConv.call(ctx, 'c1');
  assert.deepStrictEqual(r, { title: 't' });
});

test('后端明确无此会话：返回空值，可安全当作「没有」', async () => {
  // 成功响应但不含 conv：这是「后端确实没有」
  const ctx = makeCtx(async () => ({}));
  const r = await M.memLoadConv.call(ctx, 'c1');
  assert.strictEqual(r, null);
});

test('网络失败：必须与「没有」区分开', async () => {
  // 模拟 Failed to fetch
  const ctx = makeCtx(async () => { throw new Error('Failed to fetch'); });
  const r = await M.memLoadConv.call(ctx, 'c1');
  // 关键：不能返回 null——那样上层会当成「后端没有」，进而解禁写回
  assert.notStrictEqual(r, null);
  // 用对象携带失败标记，调用方据此拒绝覆盖存档
  assert.strictEqual(r.ok, false);
});
