// 模块：extend/dialog/parts/05d_memory.js
// 用途：工作记忆检查：检测到用户发言后启动计数，AI 连续多轮未写记忆时
//       产出与「回复质量检查」同形态的提醒，随卡片结果回传给 AI。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 背景：AI 应把用户提出的重要信息与当前进度实时写入 memory/ 下的当日文件，
// 但可能遗忘。这里做兜底：用户发言后开始计数，连续 MEMORY_IDLE_LIMIT 轮
// AI 输出都没有写记忆，就在最新一条助手输出上贴提醒，强制其补记。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  // 连续多少轮 AI 输出未写记忆即触发提醒
  const MEMORY_IDLE_LIMIT = 3;

  /**
   * 判断一次工具调用是否为「写记忆」操作。
   * 依据：工具为 write_to_file / replace_in_file，且路径指向 memory 目录。
   * @param {string} tool 工具名
   * @param {Object} params 调用参数
   * @returns {boolean}
   */
  M.isMemoryWriteTool = function (tool, params) {
    if (tool !== 'write_to_file' && tool !== 'replace_in_file') return false;
    const p = String((params && params.filePath) || '');
    return p.indexOf('memory') >= 0 && p.indexOf('.md') >= 0;
  };

  /**
   * 判断一组消息块中是否包含「写记忆」调用。
   * @param {Array} blocks 消息块数组
   * @returns {boolean}
   */
  M.hasMemoryWrite = function (blocks) {
    const list = window.AIMirrorDomUtils.toArray(blocks);
    for (let i = 0; i < list.length; i++) {
      const b = list[i];
      if (!b || b.type !== 'code' || !b.id) continue;
      const call = this.parseToolCall(b);
      if (call && this.isMemoryWriteTool(call.tool, call.parameters)) return true;
    }
    return false;
  };

  /**
   * 判断一条消息是否为「用户真实发言」。
   * 排除两类：外部卡片信封（external-call）、工具结果回传（bridge-chat-res）——
   * 二者虽以 user 消息落入对话，但都不是用户本人说的话。
   * @param {Object} m 消息对象
   * @returns {boolean}
   */
  M.isRealUserMessage = function (m) {
    if (!m || m.role !== 'user') return false;
    if (this.parseExternalCall(m)) return false;
    const blocks = window.AIMirrorDomUtils.toArray(m.blocks);
    for (let i = 0; i < blocks.length; i++) {
      const b = blocks[i];
      if (!b) continue;
      const s = String(b.code || b.text || '');
      if (s.indexOf('bridge-chat-res') >= 0) return false;
    }
    return true;
  };

  /** 检测到用户发言：启动记忆检查（幂等，已在检查中不重置计数）。 */
  M.armMemoryCheck = function () {
    if (!this.memoryCheck) this.memoryCheck = { armed: false, idle: 0 };
    if (!this.memoryCheck.armed) {
      this.memoryCheck.armed = true;
      this.memoryCheck.idle = 0;
      log('记忆检查：已启动（检测到用户发言）');
    }
  };

  /**
   * 推进一轮计数。
   * @param {boolean} wroteMemory 本轮是否写了记忆
   * @returns {boolean} 是否应触发提醒
   */
  M.tickMemoryCheck = function (wroteMemory) {
    if (!this.memoryCheck || !this.memoryCheck.armed) return false;
    if (wroteMemory) {
      this.memoryCheck.idle = 0;
      return false;
    }
    if (this.memoryCheck.idle >= MEMORY_IDLE_LIMIT) return true;
    this.memoryCheck.idle += 1;
    return this.memoryCheck.idle >= MEMORY_IDLE_LIMIT;
  };

  /**
   * 整轮记忆检查：仅在本轮为 generate 且存在可回传的工具卡片时判定。
   * 提醒需依附工具卡片回传，本轮若无工具调用卡片则无法送达，此时不消耗计数。
   * @param {Array} incoming 本轮消息切片
   * @param {string} reason 触发来源
   * @returns {Object|null} { error, message } 或 null
   */
  M.memoryIssueForRound = function (incoming, reason) {
    if (reason !== 'generate') return null;
    const hasToolCard = incoming.some((m) => m.role === 'assistant'
      && window.AIMirrorDomUtils.toArray(m.blocks).some((b) => b && b.type === 'code' && b.id && this.parseToolCall(b)));
    if (!hasToolCard) return null;
    const wrote = incoming.some((m) => m.role === 'assistant' && this.hasMemoryWrite(m.blocks));
    return this.memoryIssueIfStale(wrote);
  };

  /**
   * 记忆检查：若连续多轮未写记忆，返回一条提醒（与回复质量检查同形态）。
   * @param {boolean} wroteMemory 本轮是否写了记忆
   * @returns {Object|null} { error, message } 或 null
   */
  M.memoryIssueIfStale = function (wroteMemory) {
    if (!this.memoryCheck || !this.memoryCheck.armed) return null;
    if (!this.tickMemoryCheck(wroteMemory)) return null;
    log('记忆检查：连续多轮未写记忆，触发提醒');
    return {
      error: 'memory_stale',
      message: '已连续多轮未更新工作记忆。请把用户提出的重要信息与当前进度'
        + '写入 memory/ 下的当日文件（格式见 rules/work-memory.md）后再继续。'
    };
  };
})();
