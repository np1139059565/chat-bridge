// 模块：extend/dialog/parts/05e_quality.js
// 用途：助手回复的质量检测：只含代码块、思考内容非中文、语音朗读缺失。
//       检测结果作为该条消息上卡片的结果回传给 AI，促其重新生成。
//       每类检测都有独立开关（bridgePush.check_*），用户可自主决定是否检测。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 设计要点（漏告警修复）：
//   三个检测全部跑完、收集所有问题，再合成一条复合告警返回——
//   而非「命中一个就 return」。原实现里「只含代码块」或「思考英文」会
//   短路掉语音缺失检测，导致「缺语音却不告警」。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /**
   * 判定一条助手消息的质量问题，收集全部命中项后合成一条复合告警。
   * 返回 null 表示无问题，否则返回 { error, message, severity, scope? }。
   * 多项同时命中时：error 取首个，message 逐条拼接，severity 取最严重者。
   * @param {Object} m 消息对象
   * @returns {Object|null}
   */
  M.assistantQualityIssue = function (m) {
    if (!m || m.role !== 'assistant') return null;
    const blocks = window.AIMirrorDomUtils.toArray(m.blocks);
    if (!blocks.length) return null;
    const found = [];
    // 逐项检测，各自把命中项压入 found，不提前返回
    const one = this._checkCodeOnly(blocks);
    if (one) found.push(one);
    const two = this._checkThinkingEnglish(blocks);
    if (two) found.push(two);
    const three = this._checkVoiceMissing(blocks);
    if (three) found.push(three);
    if (!found.length) return null;
    if (found.length === 1) return found[0];
    // 多项命中：合成一条复合告警，保持调用方（一次只处理一个 issue）不变
    return {
      error: found[0].error,
      // 复合告警属整条回复属性，走消息级回传；含语音缺失时更是如此
      scope: found.some((f) => f.scope === 'message') ? 'message' : found[0].scope,
      // 有 fatal 取 fatal，否则 advisory
      severity: found.some((f) => f.severity === 'fatal') ? 'fatal' : 'advisory',
      message: found.map((f) => f.message).join('\n')
    };
  };

  /**
   * 检测一：只含代码块，没有任何文字说明。
   * @returns {Object|null} 命中项
   */
  M._checkCodeOnly = function (blocks) {
    if ((this.bridgePush || {}).check_code_only === false) return null;
    const hasCode = blocks.some((b) => b && b.type === 'code');
    const hasText = blocks.some((b) => {
      if (!b || b.type === 'code' || b.type === 'thinking') return false;
      let s = '';
      if (b.text != null) s = String(b.text);
      else if (b.items) s = window.AIMirrorDomUtils.toArray(b.items).join(' ');
      else if (b.rows) s = JSON.stringify(b.rows);
      return s.trim().length > 0;
    });
    if (hasCode && !hasText) {
      return {
        error: 'code_only_reply',
        severity: 'advisory',
        message: '本条回复只包含代码块，缺少文字说明，无法监控流程。'
          + '请在代码块之外补充说明再重新生成。'
      };
    }
    return null;
  };

  /**
   * 检测二：思考内容大段英文。
   * @returns {Object|null} 命中项
   */
  M._checkThinkingEnglish = function (blocks) {
    if ((this.bridgePush || {}).check_thinking === false) return null;
    const think = blocks.find((b) => b && b.type === 'thinking');
    if (!think) return null;
    const t = String(think.text || '');
    const letters = (t.match(/[A-Za-z]/g) || []).length;
    const total = t.replace(/\s/g, '').length;
    if (total > 200 && letters / total > 0.8) {
      return {
        error: 'thinking_english',
        scope: 'message',
        severity: 'advisory',
        message: '本条回复的思考内容以英文为主（约 ' + Math.round(letters / total * 100)
          + '% 为英文字符），无法监控流程。请用中文重新生成。'
      };
    }
    return null;
  };

  /**
   * 检测三：语音开关打开期间，回复必须带语音朗读块（供合成语音发回）。
   * 判定与工具调用块同一机制——认代码块内容里的 JSON type 字段，不看语言名。
   * 语音块内容形如 {"type":"bridge-voice","text":"适合朗读的口语"}。
   * @returns {Object|null} 命中项
   */
  M._checkVoiceMissing = function (blocks) {
    const voiceOn = !!(this.bridgePush && this.bridgePush.voice);
    if (!voiceOn) return null;
    const hasVoice = blocks.some((b) => this.parseVoiceBlock(b));
    if (hasVoice) return null;
    return {
      error: 'voice_missing',
      scope: 'message',
      severity: 'advisory',
      message: '本条回复缺少语音朗读文本。请另用一个代码块，块内为 JSON：'
        + '{"type":"bridge-voice","text":"适合朗读的纯口语文本"}，然后重新生成。'
    };
  };
})();
