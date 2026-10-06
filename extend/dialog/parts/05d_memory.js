// 模块：extend/dialog/parts/05d_memory.js
// 用途：记忆确认提醒：检测到用户发言后开始数 AI 的生成轮次，
//       连续多轮未确认记忆时产出与「回复质量检查」同形态的提醒，
//       随卡片结果回传给 AI，促其调用 memory_search 确认一次记忆情况。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 与旧版（文件记忆系统）的差异：
//   旧版靠比对 memory/ 目录「内容指纹」判断 AI 有没有写记忆文件——
//   因为那时记忆由 AI 主动写文件维护。新系统改为后端自动蒸馏入库，
//   AI 不再主动写文件，文件指纹判据失效，故本版改为「纯轮次计数」：
//   用户发言即开窗，此后每轮 AI 生成都计数，达到阈值就提醒一次，
//   引导 AI 用 memory_search 工具回查记忆，而非去写文件。
//
// 计数语义（关键）：
//   - 用户发言 = 打开一个计数窗口（重置计数），此后开始数 AI 的生成轮次；
//   - 窗口内每轮 AI 生成都计数；
//   - 一个窗口内最多提醒一次（notified 标记）：提醒后不再重复打扰，
//     直到用户下一次发言才重开窗口。这样用户停止说话、AI 一直跑工具时，
//     不会被反复提醒。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  // 连续多少轮 AI 生成未确认记忆即触发提醒（用户要求：三轮）
  const MEMORY_IDLE_LIMIT = 3;

  /** 初始化记忆检查状态（不存在时）。 */
  M._ensureMemoryState = function () {
    if (!this.memoryCheck) {
      this.memoryCheck = { armed: false, idle: 0, lastUserId: '', notified: false };
    }
    return this.memoryCheck;
  };

  /**
   * 取切片里最后一条「真实用户发言」的消息 id；没有则返回空串。
   * 工具结果回传（bridge-chat-res）虽以 user 角色落地，但被 isRealUserMessage
   * 判否，故不会误当作真实发言。
   * @param {Array} incoming 本轮消息切片
   * @returns {string} 消息 id（内容指纹）或空串
   */
  M._lastRealUserId = function (incoming) {
    const list = incoming || [];
    for (let i = list.length - 1; i >= 0; i--) {
      const m = list[i];
      if (m && m.role === 'user' && this.isRealUserMessage(m)) {
        return this.msgId(m);
      }
    }
    return '';
  };

  /**
   * 判断一条消息是否为「用户发言」。
   * 仅排除工具结果回传（bridge-chat-res）：那是工具产物，不是用户说的话。
   * 外部卡片（QQ 消息等）由用户发出，算用户发言，不排除。
   * @param {Object} m 消息对象
   * @returns {boolean}
   */
  M.isRealUserMessage = function (m) {
    if (!m || m.role !== 'user') return false;
    // 统一走 msgSource 判定来源（唯一入口）：只有非工具结果才算真实用户发言。
    // 注意 msgSource 仅对工具结果（bridge-chat-res）返回 'tool'；
    // 外部卡片（external-call）返回 'user'，故外部卡片仍算用户发言（既定要求）。
    return this.msgSource(m) !== 'tool';
  };

  /**
   * 处理本轮的用户发言：若出现「新的」真实用户发言，则打开一个新计数窗口。
   * 幂等：同一用户发言重复出现时不会重复重置；工具轮（无真实发言）直接跳过。
   * @param {Array} incoming 本轮消息切片
   * @returns {boolean} 本轮是否打开了新窗口
   */
  M.noteUserTurn = function (incoming) {
    const st = this._ensureMemoryState();
    const uid = this._lastRealUserId(incoming);
    if (!uid) return false;                       // 本轮无真实用户发言
    if (uid === st.lastUserId) return false;      // 与上一条相同，非新发言
    // 新的用户发言：打开新计数窗口
    st.armed = true;
    st.idle = 0;
    st.lastUserId = uid;
    st.notified = false;
    log('记忆检查：检测到新用户发言，打开计数窗口');
    return true;
  };

  /**
   * 推进一轮计数：窗口开启中则 +1。
   */
  M.tickMemoryCheck = function () {
    if (!this.memoryCheck || !this.memoryCheck.armed) return;
    this.memoryCheck.idle += 1;
  };

  /**
   * 本轮是否存在可承载提醒的工具卡片。提醒依附卡片回传，没有卡片就无法送达。
   * @param {Array} incoming 本轮消息切片
   * @returns {boolean}
   */
  M.hasDeliverableToolCard = function (incoming) {
    return incoming.some((m) => m.role === 'assistant'
      && window.AIMirrorDomUtils.toArray(m.blocks).some((b) => b && b.type === 'code' && b.id && this.parseToolCall(b)));
  };

  /**
   * 整轮记忆检查：仅在本轮为 AI 新鲜回复时判定。
   * 每轮推进计数；达到阈值且本轮有可承载提醒的卡片时才产出提醒。
   * 一个窗口内最多提醒一次（notified 标记），避免用户没说话时反复打扰。
   * @param {Array} incoming 本轮消息切片
   * @param {boolean} isFreshReply 本轮是否属 AI 新鲜回复
   * @returns {Object|null} { error, scope, severity, message } 或 null
   */
  M.memoryIssueForRound = function (incoming, isFreshReply) {
    if (!isFreshReply) return null;
    // 检测开关：关闭时不检测记忆（默认开，显式关才跳过）。
    if ((this.bridgePush || {}).check_memory === false) return null;
    if (!this.memoryCheck || !this.memoryCheck.armed) return null;
    // 一个窗口内最多提醒一次：提醒过就跳过，等用户下次发言再重开窗口
    if (this.memoryCheck.notified) return null;
    this.tickMemoryCheck();
    if (this.memoryCheck.idle < MEMORY_IDLE_LIMIT) return null;
    if (!this.hasDeliverableToolCard(incoming)) return null;
    // 已产出提醒：计数清零并置 notified，本轮窗口不再重复提醒
    this.memoryCheck.idle = 0;
    this.memoryCheck.notified = true;
    log('记忆检查：连续多轮未确认记忆，触发提醒');
    return {
      error: 'memory_stale',
      // 与代码块无关：记忆确认是整条回复的属性，走消息级回传。
      scope: 'message',
      // 补充类告警：不阻止工具执行，仅作提醒，附在卡片结果后一起回传。
      // 缺此字段会导致 05g_cards 落点判定两条分支都不进、告警被静默丢弃。
      severity: 'advisory',
      message: '已连续多轮未确认记忆情况。请调用 memory_search 工具，'
        + '以当前任务原文为 query 检索一次历史记忆，确认是否与用户此前的'
        + '表述、已定方案一致，再继续。'
    };
  };
})();
