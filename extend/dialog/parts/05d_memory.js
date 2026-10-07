// 模块：extend/dialog/parts/05d_memory.js
// 用途：记忆蒸馏质量提醒：把控「过往记忆的蒸馏效果」是否被 AI 主动抽检。
//       检测到用户发言后，期望 AI 立即抽检一次；此后每二十轮再抽检一次。
//       AI 若主动调用了记忆工具，则视为「自觉遵守」，本窗口免告警；
//       长时间未抽检（脱离掌控）才产出提醒，随卡片结果回传给 AI。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 设计（自遵守优先，告警兜底）：
//   规则已写入 rules/work-memory.md：AI 应在用户发言后立即 memory_inspect 抽检，
//   此后每二十轮再抽检一次，发现问题用 memory_refine 修正。
//   本检测只是「兜底」——AI 自觉就不打扰，脱离掌控才提醒。
//   这与旧版「数三轮看有没有写文件」的思路一致（主动做了就不警告），
//   但检视对象从「有没有写」升级为「蒸馏质量好不好」。
//
// 计数语义：
//   - 用户发言 = 打开窗口，置「待抽检」标记（immediatePending）；
//   - 每轮 AI 输出：若本轮调用了记忆工具 → 判为自觉，清标记、计数归零；
//   - 未调用：若仍在「待抽检」（用户发言后首次）→ 立即提醒；
//             否则计数 +1，满二十轮提醒一次。
//   - 一个「待抽检」只提醒一次；二十轮周期提醒后重新计数，避免反复打扰。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  // 距上次检查超过多少轮 AI 输出未检查即提醒（默认值，可被配置覆盖）
  const MEMORY_IDLE_LIMIT = 20;

  /**
   * 取记忆检查的轮次间隔（可配置）。
   *
   * 优先用用户配置的 check_memory_interval；非法或未配置时用默认 20。
   * 下限为 1，避免配成 0 或负数导致每轮都提醒。
   * @returns {number} 间隔轮数
   */
  M._memoryIdleLimit = function () {
    const v = parseInt((this.bridgePush || {}).check_memory_interval, 10);
    return (v > 0) ? v : MEMORY_IDLE_LIMIT;
  };

  // 记忆类工具名：AI 调用其中任一，即视为「主动抽检记忆」
  const MEMORY_TOOLS = { memory_search: 1, memory_inspect: 1, memory_refine: 1 };

  /** 初始化记忆检查状态（不存在时）。 */
  M._ensureMemoryState = function () {
    if (!this.memoryCheck) {
      this.memoryCheck = {
        armed: false,          // 是否处于计数窗口（用户发言后开启）
        lastUserId: '',        // 上次开窗的用户发言指纹（幂等去重）
        immediatePending: false, // 用户发言后是否仍在「待首次抽检」
        sinceCheck: 0,         // 距上次提醒经过的 AI 轮数
        notifiedImmediate: false, // 本窗口的「立即提醒」是否已发过
        nextKind: 'inspect',   // 下次周期提醒的类型（search / inspect 交替）
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
    // 新的用户发言：打开新窗口，等待 AI 首次抽检
    st.armed = true;
    st.lastUserId = uid;
    st.immediatePending = true;
    st.sinceCheck = 0;
    st.notifiedImmediate = false;
    log('记忆检查：检测到新用户发言，等待 AI 首次抽检');
    return true;
  };

  /**
   * 检测本轮切片中 AI 是否调用了记忆类工具。
   * 扫描 assistant 消息的代码块，解析工具调用，看工具名是否属记忆类。
   * @param {Array} incoming 本轮消息切片
   * @returns {boolean} 本轮 AI 是否主动抽检了记忆
   */
  M._touchedMemoryThisRound = function (incoming) {
    const list = incoming || [];
    for (let i = 0; i < list.length; i++) {
      const m = list[i];
      if (!m || m.role !== 'assistant') continue;
      const blocks = window.AIMirrorDomUtils.toArray(m.blocks);
      for (let j = 0; j < blocks.length; j++) {
        const b = blocks[j];
        if (!b || b.type !== 'code' || !b.id) continue;
        const call = this.parseToolCall(b);
        if (call && MEMORY_TOOLS[call.tool]) return true;
      }
    }
    return false;
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
   * 构造一条记忆提醒。
   *
   * 分两种：检索（search）与抽检（inspect）。
   *   - 检索：用户发言后的首条提醒，让 AI 回忆最近记忆、强化「当前处境」意识；
   *   - 抽检：之后的周期提醒，检查蒸馏质量是否失真。
   * 二者交替出现，避免反复刷同一句。
   * @param {string} kind 'search' 或 'inspect'
   * @returns {Object} { error, scope, severity, message }
   */
  M._memoryIssue = function (kind) {
    const message = (kind === 'search')
      ? '用户已提出新需求，请先检索最近记忆，确认当前处境后再动手。'
      : '已连续多轮未检查记忆，请抽检记忆的蒸馏质量。';
    return {
      error: 'memory_stale',
      // 与代码块无关：记忆状态是整条回复的属性，走消息级回传。
      scope: 'message',
      // 补充类告警：不阻止工具执行，仅作提醒，附在卡片结果后一起回传。
      severity: 'advisory',
      message: message
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
    // 先判 AI 是否自觉抽检：抽检了则清标记、计数归零，本轮不告警
    if (this._touchedMemoryThisRound(incoming)) {
      st.immediatePending = false;
      st.sinceCheck = 0;
      st.notifiedImmediate = true;   // 视为已完成首次抽检
      log('记忆检查：AI 已主动抽检，免告警并重置计数');
      return null;
    }
    // 未抽检：若仍在「待首次提醒」，则立即提醒一次（检索最近记忆，强化处境意识）
    if (st.immediatePending && !st.notifiedImmediate) {
      if (!this.hasDeliverableToolCard(incoming)) return null;
      st.immediatePending = false;
      st.notifiedImmediate = true;
      st.sinceCheck = 0;
      st.nextKind = 'inspect';   // 首条用了检索，下条交替为抽检
      log('记忆检查：用户发言后首次提醒（检索最近记忆）');
      return this._memoryIssue('search');
    }
    // 否则累加计数，满阈值提醒一次；两种提醒交替出现
    st.sinceCheck += 1;
    const limit = this._memoryIdleLimit();
    if (st.sinceCheck < limit) return null;
    if (!this.hasDeliverableToolCard(incoming)) return null;
    st.sinceCheck = 0;
    const kind = st.nextKind === 'search' ? 'search' : 'inspect';
    st.nextKind = (kind === 'search') ? 'inspect' : 'search';
    log('记忆检查：周期提醒（' + kind + '）');
    return this._memoryIssue(kind);
  };
})();
