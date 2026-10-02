// 模块：extend/dialog/parts/05d_memory.js
// 用途：工作记忆检查：检测到用户发言后开始数 AI 的发言轮次，
//       连续多轮未写记忆时产出与「回复质量检查」同形态的提醒，随卡片结果回传给 AI。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 「是否写了记忆」如何判定：不扫描工具调用参数，而是比较 memory 目录的
// 内容指纹（后端 /memory/fingerprint）。原因：
//   - 只看参数会把「读取」误判为「写入」；
//   - AI 可能用变量拼接路径，字符串匹配防不住；
//   - 读不改变内容、写必改变内容，指纹能准确区分，且不受路径写法影响。
//
// 计数语义（关键）：
//   - 用户发言 = 打开一个计数窗口（重置计数），此后开始数 AI 的发言轮次；
//   - 窗口内每轮 AI 生成都计数（写了记忆则计数归零）；
//   - 一个窗口内最多提醒一次（notified 标记）：提醒后不再重复打扰，
//     直到用户下一次发言才重开窗口。这样用户停止说话、AI 一直跑工具时，
//     不会被反复提醒。
//
// 时序说明：AI 写记忆通过卡片执行完成，而卡片执行发生在本轮入库之后；
// 因此本次采样与上次的差值反映「上一轮」的执行结果，检测有一轮滞后。
// 对三轮阈值而言，该滞后无实质影响。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  // 连续多少轮 AI 输出未写记忆即触发提醒
  const MEMORY_IDLE_LIMIT = 3;
  // 指纹采样超时（毫秒）：后端不可达时不能让入库流程卡死
  const FP_TIMEOUT_MS = 2000;

  /** 初始化记忆检查状态（不存在时）。 */
  M._ensureMemoryState = function () {
    if (!this.memoryCheck) {
      this.memoryCheck = { armed: false, idle: 0, lastFp: null, lastUserId: '', notified: false };
    }
    return this.memoryCheck;
  };

  /**
   * 采样 memory 目录的内容指纹。
   * 带超时保护：超时或失败一律返回 null（视为「未知」，不误判为写入）。
   * @returns {Promise<string|null>} 指纹字符串或 null
   */
  M.sampleMemoryFp = function () {
    const req = D.apiFetch(this, '/memory/fingerprint').then((data) => {
      return (data && typeof data.fingerprint === 'string') ? data.fingerprint : null;
    }).catch((e) => {
      log('记忆指纹采样失败：' + e);
      return null;
    });
    const timeout = new Promise((resolve) => { setTimeout(() => resolve(null), FP_TIMEOUT_MS); });
    return Promise.race([req, timeout]);
  };

  /**
   * 采样指纹并与上次比较，判断「上一轮」是否写入了记忆。
   * @returns {Promise<boolean>} 上一轮是否写入记忆
   */
  M.resolveMemoryWrote = async function () {
    const fp = await this.sampleMemoryFp();
    if (fp === null) return false;              // 采样失败：不判为写入
    if (this.memoryCheck.lastFp === null) {     // 首轮：仅建立基线
      this.memoryCheck.lastFp = fp;
      return false;
    }
    const wrote = fp !== this.memoryCheck.lastFp;
    this.memoryCheck.lastFp = fp;
    return wrote;
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
    st.lastFp = null;
    st.lastUserId = uid;
    st.notified = false;
    log('记忆检查：检测到新用户发言，打开计数窗口');
    return true;
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
    // 直接调函数而非读 m.source 字段——切片阶段消息尚未挂上树节点字段。
    return this.msgSource(m) !== 'tool';
  };

  /**
   * 推进一轮计数：写入记忆则清零，否则累加。
   * @param {boolean} wroteMemory 本轮是否写了记忆
   */
  M.tickMemoryCheck = function (wroteMemory) {
    if (!this.memoryCheck || !this.memoryCheck.armed) return;
    if (wroteMemory) this.memoryCheck.idle = 0;
    else this.memoryCheck.idle += 1;
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
   * 整轮记忆检查：仅在本轮为 generate 时判定。
   * 每轮采样指纹并推进计数；达到阈值且本轮有可承载提醒的卡片时才产出提醒。
   * 一个窗口内最多提醒一次（notified 标记），避免用户没说话时反复打扰。
   * @param {Array} incoming 本轮消息切片
   * @param {string} reason 触发来源
   * @returns {Promise<Object|null>} { error, message } 或 null
   */
  M.memoryIssueForRound = async function (incoming, reason) {
    if (reason !== 'generate') return null;
    // 检测开关：关闭时不检测记忆（默认开，显式关才跳过）。
    if ((this.bridgePush || {}).check_memory === false) return null;
    if (!this.memoryCheck || !this.memoryCheck.armed) return null;
    // 一个窗口内最多提醒一次：提醒过就跳过，等用户下次发言再重开窗口
    if (this.memoryCheck.notified) return null;
    const wrote = await this.resolveMemoryWrote();
    this.tickMemoryCheck(wrote);
    if (this.memoryCheck.idle < MEMORY_IDLE_LIMIT) return null;
    if (!this.hasDeliverableToolCard(incoming)) return null;
    // 已产出提醒：计数清零并置 notified，本轮窗口不再重复提醒
    this.memoryCheck.idle = 0;
    this.memoryCheck.notified = true;
    log('记忆检查：连续多轮未写记忆，触发提醒');
    return {
      error: 'memory_stale',
      // 与代码块无关：记忆滞后是整条回复的属性，走消息级回传。
      scope: 'message',
      // 补充类告警：不阻止工具执行，仅作提醒，附在卡片结果后一起回传。
      // 缺此字段会导致 05g_cards 落点判定两条分支都不进、告警被静默丢弃。
      severity: 'advisory',
      message: '已连续多轮未更新工作记忆。请把用户提出的重要信息与当前进度'
        + '写入 memory/ 下的当日文件（格式见 rules/work-memory.md）后再继续。'
    };
  };
})();
