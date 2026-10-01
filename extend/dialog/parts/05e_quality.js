// 模块：extend/dialog/parts/05e_quality.js
// 用途：助手回复的质量检测：只含代码块、思考内容非中文等。
//       检测结果作为该条消息上卡片的结果回传给 AI，促其重新生成。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /**
   * 判定一条助手消息的质量问题。返回 null 表示无问题，否则返回问题描述。
   * @param {Object} m 消息对象
   * @returns {Object|null} { error, message }
   */
  M.assistantQualityIssue = function (m) {
    if (!m || m.role !== 'assistant') return null;
    const blocks = window.AIMirrorDomUtils.toArray(m.blocks);
    if (!blocks.length) return null;
    // 问题一：只有代码块，没有任何文字说明
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
        message: '本条回复只包含代码块，缺少文字说明，无法监控流程。'
          + '请在代码块之外补充说明再重新生成。'
      };
    }
    // 问题二：思考内容大段英文
    const think = blocks.find((b) => b && b.type === 'thinking');
    if (think) {
      const t = String(think.text || '');
      const letters = (t.match(/[A-Za-z]/g) || []).length;
      const total = t.replace(/\s/g, '').length;
      if (total > 200 && letters / total > 0.8) {
        return {
          error: 'thinking_english',
          message: '本条回复的思考内容以英文为主（约 ' + Math.round(letters / total * 100)
            + '% 为英文字符），无法监控流程。请用中文重新生成。'
        };
      }
    }
    // 问题三：语音开关打开期间，每一轮回复都必须带语音朗读块（供合成语音发回）。
    // 判定与「代码块识别」同一套逻辑——只看是不是代码块，不看语言名：
    // 代码块识别从不依赖语言名（靠内容判别），而语言名在部分站点解析不到，
    // 若以语言名判 voice 必误报。故：排除工具调用块（内容为含 bridge-chat-call 的 JSON），
    // 其余代码块即视为语音朗读块。
    const voiceOn = !!(this.bridgePush && this.bridgePush.voice);
    if (voiceOn) {
      const hasVoice = blocks.some((b) => b && b.type === 'code'
        && !this.parseToolCall(b));
      if (!hasVoice) {
        return {
          error: 'voice_missing',
          message: '本条回复缺少语音朗读文本。请另用一个 Markdown 代码块，'
            + '块内放适合朗读的纯口语文本，然后重新生成。'
        };
      }
    }
    return null;
  };
})();
