// 模块：extend/dialog/parts/05d_memory.js
// 用途：工作记忆检查：检测到用户发言后启动计数，AI 连续多轮未写记忆时
//       产出与「回复质量检查」同形态的提醒，随卡片结果回传给 AI。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 「是否写了记忆」如何判定：不扫描工具调用参数，而是比较 memory 目录的
// 内容指纹（后端 /memory/fingerprint）。原因：
//   - 只看参数会把「读取」误判为「写入」；
//   - AI 可能用变量拼接路径，字符串匹配防不住；
//   - 读不改变内容、写必改变内容，指纹能准确区分，且不受路径写法影响。
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
   * 判定本轮是否出现「新的用户发言」，并记下最新一条的 id。
   *
   * 为什么需要它：ingestMessages 收到的 incoming 是全量可见切片，里面几乎
   * 总能看到历史用户发言，若只用「有没有用户发言」判断，工具结果回传、AI
   * 再次生成等每一轮都会被当成有效输入，导致计数被推满、提前弹提醒。
   * 这里改用「最新一条用户发言的 id 是否变化」作为唯一判据：只有用户真的
   * 说了新话，id 才会变，才算一轮。工具结果轮、重复生成轮都不变，故不计。
   * @param {Array} incoming 本轮消息切片（全量可见）
   * @returns {boolean} 本轮是否出现了新的用户发言
   */
  M.noteUserTurn = function (incoming) {
    const list = incoming || [];
    // 取切片里最后一条 user 消息，判断它是否为真正的用户发言。
    // 工具结果回传（bridge-chat-res）也以 user 消息落地，且总排在真实用户发言
    // 之后，因此它是「工具结果轮」时，最后一条 user 消息会被 isRealUserMessage
    // 判否；只有用户真的说了新话，末条 user 消息才是真实发言。
    for (let i = list.length - 1; i >= 0; i--) {
      const m = list[i];
      if (m && m.role === 'user') return this.isRealUserMessage(m);
    }
    return false;
  };

  /** 检测到新用户发言：启动记忆检查（幂等，已在检查中不重置计数）。 */
  M.armMemoryCheck = function () {
    if (!this.memoryCheck) {
      this.memoryCheck = { armed: false, idle: 0, lastFp: null };
    }
    if (!this.memoryCheck.armed) {
      this.memoryCheck.armed = true;
      this.memoryCheck.idle = 0;
      this.memoryCheck.lastFp = null;
      log('记忆检查：已启动（检测到新用户发言）');
    }
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
    const blocks = window.AIMirrorDomUtils.toArray(m.blocks);
    for (let i = 0; i < blocks.length; i++) {
      const b = blocks[i];
      if (!b) continue;
      const s = String(b.code || b.text || '');
      if (s.indexOf('bridge-chat-res') >= 0) return false;
    }
    return true;
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
   * @param {Array} incoming 本轮消息切片
   * @param {string} reason 触发来源
   * @returns {Promise<Object|null>} { error, message } 或 null
   */
  M.memoryIssueForRound = async function (incoming, reason) {
    if (reason !== 'generate') return null;
    if (!this.memoryCheck || !this.memoryCheck.armed) return null;
    // 只有用户真的说了新话，才算一轮有效输入并推进计数；
    // 工具结果回传、AI 重复生成等没有新用户发言的轮次直接跳过，
    // 既不采样指纹也不累加 idle，从根本上消除「工具结果也触发提醒」。
    if (!this.noteUserTurn(incoming)) {
      log('记忆检查：本轮无新用户发言，跳过计数');
      return null;
    }
    const wrote = await this.resolveMemoryWrote();
    this.tickMemoryCheck(wrote);
    if (this.memoryCheck.idle < MEMORY_IDLE_LIMIT) return null;
    if (!this.hasDeliverableToolCard(incoming)) return null;
    // 已产出提醒：计数清零，若 AI 仍不写，三轮后再次提醒
    this.memoryCheck.idle = 0;
    log('记忆检查：连续多轮未写记忆，触发提醒');
    return {
      error: 'memory_stale',
      message: '已连续多轮未更新工作记忆。请把用户提出的重要信息与当前进度'
        + '写入 memory/ 下的当日文件（格式见 rules/work-memory.md）后再继续。'
    };
  };
})();
