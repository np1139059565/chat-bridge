// 模块：extend/dialog/parts/05d_memory.js
// 用途：记忆「先检索、后抽检」提醒：先引导 AI 检索记忆用于规划，再把控蒸馏质量。
//       检测到用户发言后，期望 AI 先调 memory_search 检索；此后每二十轮再随机提醒
//       「检索」或「抽检」一次。AI 若主动做了，本窗口免告警；
//       长时间未做（脱离掌控）才产出提醒，随卡片结果回传给 AI。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 设计（自遵守优先，告警兜底）：
//   本检测只负责产出提醒；提醒会作为质量门禁挂在工具卡片上，
//   从而阻止该工具执行、把提醒当作结果回传（见 05g_cards._decideIssueTarget）。
//   检索与抽检是两件事：
//   - 检索（memory_search）：用记忆——取回最近相关记忆精华，校准处境、消除臆测、再规划；
//   - 抽检（memory_inspect/refine）：保质量——检查蒸馏是否失真，失真则修正。
//
// 计数语义：
//   - 用户发言 = 打开窗口，置「待检索」（retrievePending）标记；
//   - 每轮 AI 输出：调了检索工具 → 清检索标记；调了抽检工具 → 计数归零；
//   - 优先级：用户发言后先提醒检索（retrieve）——首次检测到工具调用而尚未检索时，
//     拦截该次调用并引导先检索（仅一次，防死循环）；
//     此后计数满二十轮，随机在「抽检 / 检索」中提醒一类（periodic）。
//   - 每类提醒一个窗口只发一次，避免反复打扰与死循环。
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
        sinceCheck: 0,         // 距上次周期提醒经过的 AI 轮数
        notifiedRetrieve: false, // 本窗口的「检索提醒」是否已发过（一次，避免死循环）
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
    // 新的用户发言：打开新窗口，等待 AI 先检索
    st.armed = true;
    st.lastUserId = uid;
    st.retrievePending = true;      // 先引导检索（拿最近记忆、强化处境、再规划）
    st.sinceCheck = 0;
    st.notifiedRetrieve = false;
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
   * @param {string} why 触发原因（retrieve / periodic_inspect / periodic_retrieve）
   * @returns {Object} { error, scope, severity, message }
   */
  M._memoryIssue = function (why) {
    // 四类提醒：retrieve（用户发言后先检索）/ periodic_inspect（周期抽检）
    //          / periodic_retrieve（周期检索）。后两者由轮次随机择一。
    let head;
    if (why === 'retrieve') {
      head = '用户已提出新需求，但你尚未检索记忆。请先调用 memory_search：'
        + '取回最近若干轮（约五轮）的最后记忆节点内容——其中既有上一任务的蒸馏结论，'
        + '也有当前任务已沉淀的记忆。据此校准当前处境、消除臆测，再规划新任务。';
    } else if (why === 'periodic_retrieve') {
      head = '已连续多轮未检索记忆。请调用 memory_search：'
        + '取回最近若干轮（约五轮）的最后记忆节点内容——既有上一任务的蒸馏结论，'
        + '也有当前任务已沉淀的记忆。据此校准当前处境，再继续推进。';
    } else {
      head = '已连续多轮未抽检记忆的蒸馏质量，请调用 memory_inspect 抽检一次。';
    }
    return {
      // 检索类归 memory_unread，抽检类归 memory_stale
      error: (why === 'retrieve' || why === 'periodic_retrieve') ? 'memory_unread' : 'memory_stale',
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

    // 先消化「本轮已做的动作」：检索与抽检各自清各自的标记。
    if (this._retrievedMemoryThisRound(incoming)) {
      st.retrievePending = false;   // 本窗口的检索引导已完成
      log('记忆检查：AI 已检索记忆，检索待办清除');
    }
    if (this._inspectedMemoryThisRound(incoming)) {
      st.sinceCheck = 0;            // 主动抽检 → 周期计数归零
      log('记忆检查：AI 已抽检记忆，计数归零');
    }

    // 优先级一：用户发言后，首次检测到工具调用而尚未检索 → 拦截该次调用并引导检索。
    // 仅一次：拦截后即置标记，之后不再反复告警，避免 AI 不检索时被反复拦下造成死循环。
    if (st.retrievePending && !st.notifiedRetrieve) {
      if (!this.hasDeliverableToolCard(incoming)) return null;
      st.notifiedRetrieve = true;   // 一个窗口只引导一次，防死循环
      log('记忆检查：用户发言后尚未检索，引导检索并拦截该次工具');
      return this._memoryIssue('retrieve');
    }

    // 优先级二：此后每 MEMORY_IDLE_LIMIT 轮，在「抽检 / 检索」中随机提醒一类。
    st.sinceCheck += 1;
    if (st.sinceCheck < MEMORY_IDLE_LIMIT) return null;
    if (!this.hasDeliverableToolCard(incoming)) return null;
    st.sinceCheck = 0;
    const pickRetrieve = Math.random() < 0.5;   // 50% 概率提醒检索
    log('记忆检查：连续多轮未处理，周期提醒（' + (pickRetrieve ? '检索' : '抽检') + '）');
    return this._memoryIssue(pickRetrieve ? 'periodic_retrieve' : 'periodic_inspect');
  };
})();
