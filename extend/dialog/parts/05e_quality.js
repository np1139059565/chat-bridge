// 模块：extend/dialog/parts/05e_quality.js
// 用途：助手回复的质量检测：只含代码块、思考内容非中文等。
//       检测结果作为该条消息上卡片的结果回传给 AI，促其重新生成。
//       每类检测都有独立开关（bridgePush.check_*），用户可自主决定是否检测。
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
    // 检测开关集合：默认开，显式关才跳过（防止旧存档缺字段时误关）。
    const checks = this.bridgePush || {};
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
    if (hasCode && !hasText && checks.check_code_only !== false) {
      return {
        error: 'code_only_reply',
        // scope：问题归属。'block' 表示该检测天生依赖代码块，只能随代码块卡片回传；
        // 'message' 表示与代码块无关，改走消息级回传（见 05g_cards.js 的分流）。
        scope: 'block',
        message: '本条回复只包含代码块，缺少文字说明，无法监控流程。'
          + '请在代码块之外补充说明再重新生成。'
      };
    }
    // 问题二：思考内容大段英文
    const think = blocks.find((b) => b && b.type === 'thinking');
    if (think && checks.check_thinking !== false) {
      const t = String(think.text || '');
      const letters = (t.match(/[A-Za-z]/g) || []).length;
      const total = t.replace(/\s/g, '').length;
      if (total > 200 && letters / total > 0.8) {
        return {
          error: 'thinking_english',
          // 与代码块无关：思考内容属于整条回复的属性，走消息级回传。
          scope: 'message',
          message: '本条回复的思考内容以英文为主（约 ' + Math.round(letters / total * 100)
            + '% 为英文字符），无法监控流程。请用中文重新生成。'
        };
      }
    }
    // 问题三：语音开关打开期间，每一轮回复都必须带语音朗读块（供合成语音发回）。
    // 判定与工具调用块同一机制——认代码块内容里的 JSON type 字段，不看语言名。
    // 语音块内容形如 {"type":"bridge-voice","text":"适合朗读的口语"}。
    // 开关即 bridgePush.voice：关闭语音识别功能时，本检测自然不跑。
    const voiceOn = !!(this.bridgePush && this.bridgePush.voice);
    if (voiceOn) {
      const hasVoice = blocks.some((b) => this.parseVoiceBlock(b));
      if (!hasVoice) {
        return {
          error: 'voice_missing',
          // 与代码块无关：语音朗读缺失是整条回复的属性，走消息级回传。
          // 这样纯文字回复（无任何代码块）也能收到该提示并重新生成。
          scope: 'message',
          message: '本条回复缺少语音朗读文本。请另用一个代码块，块内为 JSON：'
            + '{"type":"bridge-voice","text":"适合朗读的纯口语文本"}，然后重新生成。'
        };
      }
    }
    return null;
  };
})();
