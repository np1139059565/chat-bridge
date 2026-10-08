// 模块：extend/dialog/parts/05d_memory.js
// 用途：记忆「先检索、后抽检」提醒：先引导 AI 检索记忆用于规划，再把控蒸馏质量。
//       检测到用户发言后，期望 AI 先调 memory_search 检索；随后抽检一次蒸馏质量；
//       此后每二十轮再抽检一次。AI 若主动做了，本窗口免告警；
//       长时间未做（脱离掌控）才产出提醒，随卡片结果回传给 AI。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 设计（自遵守优先，告警兜底）：
//   本检测只负责产出提醒；AI 收到提醒后，据提醒内容自行调用记忆工具处理。
//   检索与抽检是两件事：
//   - 检索（memory_search）：用记忆——取回最近相关记忆精华，校准处境、消除臆测、再规划；
//   - 抽检（memory_inspect/refine）：保质量——检查蒸馏是否失真，失真则修正。
//   本检测只是「兜底」——AI 自觉就不打扰，脱离掌控才提醒。
//
// 计数语义：
//   - 用户发言 = 打开窗口，置「待检索」（retrievePending）与「待抽检」（inspectPending）两个标记；
//   - 每轮 AI 输出：调了检索工具 → 清检索标记；调了抽检工具 → 清抽检标记、计数归零；
//   - 优先级：先提醒检索（retrieve）→ 检索做了再提醒首次抽检（immediate）→ 之后计数满二十轮周期提醒（periodic）。
//   - 每类提醒一个窗口只发一次，避免反复打扰。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  // 距上次抽检超过多少轮 AI 输出未抽检即提醒（用户要求：二十轮）
  const MEMORY_IDLE_LIMIT = 20;

  // 检索类工具：AI 调用即视为「已完成本轮记忆检索」
  const RETRIEVE_TOOLS = { memory_search: 1 };
  // 抽检类工具：AI 调用即视为「已主动抽检蒸馏质量」
  const INSPECT_TOOLS = { memory_inspect: 1, memory_refine: 1 };

  /** 初始化记忆检查状态（不存在时）。 */
  M._ensureMemoryState = function () {
    if (!this.memoryCheck) {
      this.memoryCheck = {
        armed: false,          // 是否处于计数窗口（用户发言后开启）
        lastUserId: '',        // 上次开窗的用户发言指纹（幂等去重）
        retrievePending: false, // 用户发言后是否仍「待首次检索」
        inspectPending: false,  // 用户发言后是否仍「待首次抽检」
        sinceCheck: 0,         // 距上次抽检经过的 AI 轮数
        notifiedRetrieve: false, // 本窗口的「检索提醒」是否已发过
        notifiedImmediate: false, // 本窗口的「抽检立即提醒」是否已发过
      };
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
    return this.msgSource(m) !== 'tool';
  };

  /**
   * 处理本轮的用户发言：若出现「新的」真实用户发言，则打开一个新窗口。
   * 幂等：同一用户发言重复出现时不会重复重置；工具轮（无真实发言）直接跳过。
   * @param {Array} incoming 本轮消息切片
   * @returns {boolean} 本轮是否打开了新窗口
   */
  M.noteUserTurn = function (incoming) {
    const st = this._ensureMemoryState();
    const uid = this._lastRealUserId(incoming);
    if (!uid) return false;                       // 本轮无真实用户发言
    if (uid === st.lastUserId) return false;      // 与上一条相同，非新发言
    // 新的用户发言：打开新窗口，等待 AI 先检索、后抽检
    st.armed = true;
    st.lastUserId = uid;
    st.retrievePending = true;      // 先引导检索（拿最近记忆、强化处境、再规划）
    st.inspectPending = true;       // 之后仍需一次抽检
    st.sinceCheck = 0;
    st.notifiedRetrieve = false;
    st.notifiedImmediate = false;
    log('记忆检查：检测到新用户发言，等待 AI 首次检索');
    return true;
  };

  /**
   * 检测本轮切片中 AI 是否调用了记忆类工具。
   * 扫描 assistant 消息的代码块，解析工具调用，看工具名是否属记忆类。
   * @param {Array} incoming 本轮消息切片
   * @returns {boolean} 本轮 AI 是否主动抽检了记忆
   */
  M._touchedMemoryThisRound = function (incoming, toolSet) {
    const list = incoming || [];
    for (let i = 0; i < list.length; i++) {
      const m = list[i];
      if (!m || m.role !== 'assistant') continue;
      const blocks = window.AIMirrorDomUtils.toArray(m.blocks);
      for (let j = 0; j < blocks.length; j++) {
        const b = blocks[j];
        if (!b || b.type !== 'code' || !b.id) continue;
        const call = this.parseToolCall(b);
        if (call && toolSet[call.tool]) return true;
      }
    }
    return false;
  };

  /**
   * 本轮 AI 是否调用了检索类工具（memory_search）。
   * @param {Array} incoming 本轮消息切片
   * @returns {boolean}
   */
  M._retrievedMemoryThisRound = function (incoming) {
    return this._touchedMemoryThisRound(incoming, RETRIEVE_TOOLS);
  };

  /**
   * 本轮 AI 是否调用了抽检类工具（memory_inspect / memory_refine）。
   * @param {Array} incoming 本轮消息切片
   * @returns {boolean}
   */
  M._inspectedMemoryThisRound = function (incoming) {
    return this._touchedMemoryThisRound(incoming, INSPECT_TOOLS);
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
   * 构造一条记忆质量提醒。
   * @param {string} why 触发原因（immediate / periodic）
   * @returns {Object} { error, scope, severity, message }
   */
  M._memoryIssue = function (why) {
    // 三类提醒：retrieve（先检索）/ immediate（首次抽检）/ periodic（周期抽检）
    let head;
    if (why === 'retrieve') {
      head = '用户已提出新需求，但你尚未检索记忆。请先调用 memory_search：'
        + '以当前任务原文为查询，取回最近相关记忆（含蒸馏精华），'
        + '据此校准当前处境、消除臆测，再规划新任务。';
    } else if (why === 'immediate') {
      head = '用户已提出新需求，但你尚未抽检记忆的蒸馏质量。'
        + '请调用 memory_inspect 抽检「过往」记忆（对比原文与精华），'
        + '若发现精华失真或关键词无效，用 memory_refine 修正。';
    } else {
      head = '已连续多轮未抽检记忆的蒸馏质量，请调用 memory_inspect 抽检一次。';
    }
    return {
      error: (why === 'retrieve') ? 'memory_unread' : 'memory_stale',
      // 与代码块无关：记忆质量是整条回复的属性，走消息级回传。
      scope: 'message',
      // 补充类告警：不阻止工具执行，仅作提醒，附在卡片结果后一起回传。
      severity: 'advisory',
      message: head
    };
  };

  /**
   * 整轮记忆检查：仅在本轮为 AI 新鲜回复时判定。
   * 每轮先判 AI 是否主动抽检：抽检则清标记、计数归零；未抽检则按
   * 「待首次抽检 → 立即提醒」「否则每二十轮提醒」两种节奏产出提醒。
   * @param {Array} incoming 本轮消息切片
   * @param {boolean} isFreshReply 本轮是否属 AI 新鲜回复
   * @returns {Object|null} { error, scope, severity, message } 或 null
   */
  M.memoryIssueForRound = function (incoming, isFreshReply) {
    if (!isFreshReply) return null;
    // 保守判定：仅当开关明确为 true 才检测（与 05e_quality 各检测一致）。
    if ((this.bridgePush || {}).check_memory !== true) return null;
    const st = this.memoryCheck;
    if (!st || !st.armed) return null;

    // 先消化「本轮已做的动作」：检索与抽检各自清各自的待办标记。
    if (this._retrievedMemoryThisRound(incoming)) {
      st.retrievePending = false;
      st.notifiedRetrieve = true;   // 本窗口的检索引导已完成
      log('记忆检查：AI 已检索记忆，检索待办清除');
    }
    if (this._inspectedMemoryThisRound(incoming)) {
      st.inspectPending = false;
      st.sinceCheck = 0;
      st.notifiedImmediate = true;  // 视为已完成首次抽检
      log('记忆检查：AI 已抽检记忆，计数归零');
    }

    // 优先级一：用户发言后，先引导「检索」——拿最近记忆、校准处境、再规划。
    // 检索与抽检是两件事，检索未做前不急着催抽检。
    if (st.retrievePending && !st.notifiedRetrieve) {
      if (!this.hasDeliverableToolCard(incoming)) return null;
      st.notifiedRetrieve = true;   // 一个窗口只引导一次，不反复打扰
      log('记忆检查：用户发言后尚未检索，引导检索');
      return this._memoryIssue('retrieve');
    }

    // 优先级二：检索已做，但仍需一次抽检（首次）
    if (st.inspectPending && !st.notifiedImmediate) {
      if (!this.hasDeliverableToolCard(incoming)) return null;
      st.notifiedImmediate = true;
      st.sinceCheck = 0;
      log('记忆检查：尚未抽检，立即提醒');
      return this._memoryIssue('immediate');
    }

    // 优先级三：此后每 MEMORY_IDLE_LIMIT 轮抽检一次
    st.sinceCheck += 1;
    if (st.sinceCheck < MEMORY_IDLE_LIMIT) return null;
    if (!this.hasDeliverableToolCard(incoming)) return null;
    st.sinceCheck = 0;
    log('记忆检查：连续多轮未抽检，周期提醒');
    return this._memoryIssue('periodic');
  };
})();
