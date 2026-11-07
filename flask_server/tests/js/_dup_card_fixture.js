/* ============================================================
 * 建卡去重测试的公共夹具（相邻消息 / 同消息两套用例共用）
 *
 * 为什么独立成文件：
 *   两份去重用例的桩安装、分片加载与建卡辅助（buildAll / freshState）
 *   逐字相同，各写一份既触发跨文件重复块检测，改一处也容易漏改另一处。
 *   抽到此处后只留一份。命名约定同 _part_stub.js：以 _ 开头、
 *   不以 .test.js 结尾，不进 node --test 的执行与覆盖率统计。
 * ============================================================ */

const path = require('node:path');

const dialog = require('./_part_stub').installStub();
const ROOT = path.join(__dirname, '..', '..', '..', 'extend');
// 按依赖顺序加载被测分片：建卡在 05g，签名与末条判定是其前置依赖
require(path.join(ROOT, 'lib', 'dom-utils.js'));
['04_sessions', '05h_tree_query', '05f_parse', '05e_quality', '05j_card_sig', '05g_cards']
  .forEach((n) => require(path.join(ROOT, 'dialog', 'parts', n + '.js')));
const D = dialog;
const M = dialog.methods;

// cardInMirror 定义在 06_execute.js，该分片依赖较多（倒计时状态机等），
// 本文件只验证建卡阶段的去重，故打桩为「镜像里都存在」即可。
M.cardInMirror = function () { return true; };

/**
 * 按主循环的口径逐条建卡：每轮把「前一条消息的卡片表」交给建卡逻辑，
 * 这是相邻去重的比对基准。会话状态也要先就位——建卡会经 _executedSig 查签名库。
 *
 * @param {Array} incoming 本轮消息切片
 * @param {Object} state 建卡状态（会被就地更新）
 * @param {Array} autoCandidates 自动执行候选池（会被就地追加）
 * @returns {void}
 */
function buildAll(incoming, state, autoCandidates) {
  M.conversations = {};
  M.activeConv = 'c1';
  incoming.forEach((m, mi) => {
    const prevM = mi > 0 ? incoming[mi - 1] : null;
    state.prevCards = (prevM && prevM.cards) || null;
    M._buildCardsForOne({ msgTree: {} }, m, mi, incoming, 'generate', null, false, autoCandidates, state);
  });
}

/**
 * 造一份初始建卡状态。
 *
 * @returns {Object} 状态对象
 */
function freshState() {
  return { armedLast: null, isFreshReply: true, firstToolCard: null, prevCards: null };
}

module.exports = { dialog: dialog, buildAll: buildAll, freshState: freshState, ROOT: ROOT };
