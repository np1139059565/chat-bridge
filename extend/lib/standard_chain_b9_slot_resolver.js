/*
 * B-9 落点转换/拒绝纯函数层（独立命名，不与其它替换位模块共用文件）。
 * 只描述 M1 / M2 / M6 / M7 / M8 五槽的旧位到标准落点类型，
 * 在纯函数层实测「旧位不再生效 / 新位生效 / 异常违约不落盘无残留副作用」。
 * 运行时装配状态保持声明态。
 * 清单/映射层 STATUS 恒 declared-placeholder；本层是可实测能力，不翻 STATUS。
 * 落点类型取自 extend/lib/standard_chain_replacement_map.md 的 M1 / M2 / M6 / M7 / M8 声明。
 */
'use strict';

// 声明态：与 standard_chain_adapter.js 一致，纯函数层不改变清单/映射层状态。
var STATUS = 'declared-placeholder';
// 唯一键：标准 tool_call.id。
var KEY = 'tool_call.id';
// tool 消息三键：role / tool_call_id / content，不含消息指纹。
var TOOL_MESSAGE_KEYS = Object.freeze(['role', 'tool_call_id', 'content']);

// 五槽声明：旧位所在层、旧位标记、替换位落点类型、对应槽位与矩阵编号。
// M6 按 b6 结论只做「三网关包装 → 公共层解析」落点类型条目，不造三网关包装文件。
// M8 只描述兼容位现状。
var SLOTS = Object.freeze([
  Object.freeze({
    id: 'M1', oldLayer: '前端消息信封与工具指令包装层',
    legacy: 'bridge-chat-call', standard: '标准 tool_calls 意图位',
    criteria: 'S3', matrix: '#13', compatibleOnly: false
  }),
  Object.freeze({
    id: 'M2', oldLayer: '前端回执信封与结果合并层',
    legacy: 'bridge-chat-res', standard: 'tool 消息三键位',
    criteria: 'S3', matrix: '#13', compatibleOnly: false
  }),
  Object.freeze({
    id: 'M6', oldLayer: '三网关信封包装层',
    legacy: '三网关包装', standard: '标准信封字段位',
    criteria: 'S3', matrix: '#13', compatibleOnly: false
  }),
  Object.freeze({
    id: 'M7', oldLayer: '公共层解析与分发面',
    legacy: '公共层解析旧位', standard: '标准 tool_calls / tool 消息三键位',
    criteria: 'S1 / S2 / S3', matrix: '#4 / #7 / #13', compatibleOnly: false
  }),
  Object.freeze({
    id: 'M8', oldLayer: '刷新恢复与签名兼容层',
    legacy: '旧标记兼容位', standard: '标准 call_<nonce> 优先键',
    criteria: 'S4', matrix: '#14', compatibleOnly: true
  })
]);

// 构造拒绝结果：accepted=false，persisted=false 表示不落盘无残留副作用。
function makeReject(slot, reason, convertedTo) {
  return {
    accepted: false, status: STATUS, by: KEY, keys: TOOL_MESSAGE_KEYS,
    slot: slot, reason: reason, convertedTo: convertedTo || null, persisted: false
  };
}

// 构造规范化结果：新位生效仅在本纯函数层，输出标准落点类型与唯一键。
function makeAccept(spec, marker) {
  return {
    accepted: true, status: STATUS, by: KEY, keys: TOOL_MESSAGE_KEYS,
    slot: spec.id, oldLayer: spec.oldLayer, target: spec.standard,
    marker: marker, persisted: false
  };
}

// 按槽位 id 查声明，找不到返回 null，供违约拒绝使用。
function findSlot(id) {
  for (var i = 0; i < SLOTS.length; i += 1) {
    if (SLOTS[i].id === id) return SLOTS[i];
  }
  return null;
}

// 落点转换/拒绝主入口：旧位输入返回拒绝并附带转换建议，
// 新位输入返回规范化结果，异常或违约输入返回不落盘拒绝。
function resolveReplacement(request) {
  if (!request || typeof request !== 'object') {
    return makeReject(null, 'invalid-input', null);
  }
  var spec = findSlot(request.slot);
  if (!spec) return makeReject(request.slot || null, 'unknown-slot', null);
  var marker = String(request.marker == null ? '' : request.marker);
  if (marker === spec.legacy) {
    return makeReject(spec.id, 'legacy-slot-not-effective', spec.standard);
  }
  if (marker === spec.standard) return makeAccept(spec, marker);
  return makeReject(spec.id, 'unknown-marker', null);
}

module.exports = {
  STATUS: STATUS, KEY: KEY, TOOL_MESSAGE_KEYS: TOOL_MESSAGE_KEYS,
  SLOTS: SLOTS, findSlot: findSlot, resolveReplacement: resolveReplacement
};
