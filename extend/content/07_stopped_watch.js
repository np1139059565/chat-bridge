// 模块：extend/content/07_stopped_watch.js
// 用途：网页 AI 触发风控出现「已停止」时，自动点一次「重新生成」恢复，免去人工操作。
//
// 为什么不能写成「轮询特征是否存在」：
//   一旦生成恢复正常、收到新回复，「已停止」特征就从 DOM 消失。若按存在性轮询，
//   要么因为变化太快而漏检，要么在正常完成后误触发。
//   正确做法是捕捉「由生成中变为已停止」这一次状态流转——
//   本模块挂在生成态轮询的「生成中 → 空闲」翻转点上，正好是这个时刻。
//
// 判定依据（来自实机源码）：
//   「已停止」是思考区标题栏里的一个 span，与思考内容 .ds-think-content 是兄弟关系，
//   不在思考内容内部。故检测时排除 .ds-think-content 内部，只认标题栏里的文字。
//
// 点击由主世界执行（隔离世界受 CSP 限制无法求值），复用 06_picker 的 A.execClick。
(function () {
  'use strict';
  const A = window.AIMirror;
  if (!A) return;

  // 恢复延迟：检测到「已停止」后等这么久再点重新生成。
  // 留出余量是因为按钮可能晚一两帧才重新可用，点太早会落空。
  const RECOVER_DELAY_MS = 5000;

  // 同一轮只恢复一次：防止按钮点不动时反复重试、把页面刷成请求风暴。
  let recovering = false;

  /**
   * 判断最后一条 AI 消息的思考区标题栏里是否写着「已停止」。
   *
   * 只在标题栏找、不进思考内容里找：思考内容里也可能出现「已停止」这个词
   * （比如 AI 自己在讲这个话题），误判会导致正常回复被当成风控中断。
   *
   * @returns {boolean} 是否处于「已停止」状态
   */
  A.isStoppedByRisk = function () {
    const P = A.activeProfile();
    // 站点没配思考区选择器就没有可靠判据，直接放弃检测（不影响其它功能）
    if (!P || !P.thinking) return false;
    // 取最后一条 AI 消息：风控只会发生在最新一轮
    const msgs = document.querySelectorAll(P.item || '.ds-message');
    if (!msgs.length) return false;
    const last = msgs[msgs.length - 1];
    const think = last.querySelector(P.thinking);
    if (!think) return false;
    // 标题栏 = 思考区容器里、排除思考内容本身之后的文字
    const inner = last.querySelector('.ds-think-content');
    const full = (think.textContent || '').trim();
    const body = inner ? (inner.textContent || '').trim() : '';
    // 用「全文减去正文」近似得到标题栏文字：正文出现在标题之后，故用切片
    const header = body && full.endsWith(body) ? full.slice(0, full.length - body.length) : full;
    return header.indexOf('已停止') >= 0;
  };

  /**
   * 检测到「已停止」后延迟点一次「重新生成」。
   *
   * 由生成态轮询在「生成中 → 空闲」翻转时调用（见 04_observer.js）。
   * 只在真是风控中断时才动，正常生成结束不受影响。
   */
  A.recoverIfStopped = function () {
    if (recovering) return;
    if (!A.isStoppedByRisk()) return;
    const P = A.activeProfile();
    const expr = P && P.regenerateExpr;
    if (!expr) {
      A.warn('检测到已停止，但站点未配置重新生成表达式，无法自动恢复');
      return;
    }
    recovering = true;
    A.log && A.log('检测到「已停止」，' + (RECOVER_DELAY_MS / 1000) + ' 秒后自动重新生成');
    setTimeout(function () {
      // 点击交给主世界：隔离世界无法求值，且点击需触发页面自己的事件处理
      A.execClick(expr, 'unique', function (ok, reason) {
        recovering = false;
        if (ok) {
          A.log && A.log('自动重新生成已触发');
        } else {
          A.warn('自动重新生成失败：' + (reason || '未知原因'));
        }
      });
    }, RECOVER_DELAY_MS);
  };
})();
