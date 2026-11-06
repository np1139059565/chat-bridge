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
  // 命名空间名必须与其它内容脚本一致：window.AIMirrorContent。
  // 曾误写成 window.AIMirror，取到 undefined，下一行守卫直接 return，
  // 整个模块一个函数都没挂上——表现为「恢复函数未定义」，且没有任何报错。
  // 加载探针：
  //   「模块开始加载」没出现 → 文件根本没被注入（manifest 未生效 / 扩展未重新加载）
   //   出现但无「加载完成」   → 中途抛错，看控制台报错行
   //   两条都出现却仍报未定义 → 函数挂错了对象
  console.log('[AI-Mirror][content] [风控恢复] 模块开始加载');
  const A = window.AIMirrorContent;
  if (!A) {
    console.error('[AI-Mirror][content] [风控恢复] 命名空间 AIMirrorContent 不存在，模块中止');
    return;
  }

  // 恢复延迟：检测到异常停止后等这么久再点重新生成。
  //
  // 由 5 秒放宽到 20 秒，理由是 5 秒不够人反应：
  // 用户看到生成停住、判断是风控还是自己点错、再决定要不要重试，这个过程往往超过 5 秒。
  // 自动跑得太早，等于在用户还在犹豫时替他做了决定。20 秒足够人介入——
  // 不想恢复的话，直接点停止或切走即可，到时检测条件已不成立。
  const RECOVER_DELAY_MS = 20000;

  // 开关：默认关闭。风控自动恢复会替用户点按钮，属侵入性动作，
  // 默认不启用，由用户在扩展设置里显式打开才生效。
  // 存储键与其它界面偏好一致，用 chrome.storage.local。
  const ENABLED_KEY = 'aiMirrorRiskRecover';
  let autoRecoverEnabled = false;

  // 同一轮只恢复一次：防止按钮点不动时反复重试、把页面刷成请求风暴。
  let recovering = false;

  // 读取开关状态：页面加载时读一次，之后监听变化即时生效。
  try {
    chrome.storage.local.get([ENABLED_KEY], function (res) {
      autoRecoverEnabled = !!(res && res[ENABLED_KEY]);
    });
    chrome.storage.onChanged.addListener(function (changes, area) {
      if (area !== 'local' || !changes[ENABLED_KEY]) return;
      autoRecoverEnabled = !!changes[ENABLED_KEY].newValue;
    });
  } catch (e) {
    // 存储不可用（如权限受限）时保持默认关闭，不抛错影响其它功能
  }

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
    const msgs = document.querySelectorAll(P.item || '.ds-message');
    if (!msgs.length) return false;
    // 往前看最近三条，而不是只看最后一条。
    //
    // 为什么：风控停止时正文容器没生成，该消息会被解析成用户消息，
    // 且「已停止」文字在思考区的标题栏里——它是思考内容的兄弟节点，不在其内部。
    // 原先只看最后一条、只在思考区里找文字，两处都落空，导致检测永不成立。
    const start = Math.max(0, msgs.length - 3);
    for (let i = start; i < msgs.length; i++) {
      const nodes = msgs[i].querySelectorAll('span, div');
      for (let j = 0; j < nodes.length; j++) {
        const n = nodes[j];
        const txt = (n.textContent || '').trim();
        // 精确等于该短语，且必须不在正文 / 思考正文里——
        // 那些地方出现是在描述这个话题，不是状态提示。
        if (txt === '已停止' && !n.closest('.ds-markdown')) {
          return true;
        }
      }
    }
    return false;
  };

  /**
   * 判断最后一条 AI 消息是否「输出为空」——风控的另一种表现。
   *
   * 与「已停止」的区别：那种页面会明确显示停止字样；这种只是生成中断，
   * 末条 AI 消息里只剩思考内容，正文一个字都没有。
   *
   * 判定复用现有解析（A.makeAssistant），不另写一套 DOM 遍历：
   * 解析结果里除 thinking 外没有任何内容块，即视为空。
   * 这样站点结构变化时，只需维护解析那一处，不会出现两套判定各自漂移。
   *
   * @returns {boolean} 是否属空输出
   */
  A.isEmptyByRisk = function () {
    const P = A.activeProfile();
    if (!P || !A.makeAssistant) return false;
    const msgs = document.querySelectorAll(P.item || '.ds-message');
    if (!msgs.length) return false;
    // 往后找最近的 AI 消息，而非死盯最后一条：
    // 风控截断时最后一条可能被解析成用户消息（正文容器没生成），
    // 死盯最后一条会直接返回 false，空输出这种形态就永远检不出来。
    let target = null;
    const start = Math.max(0, msgs.length - 3);
    for (let i = msgs.length - 1; i >= start; i--) {
      if (!P.assistantMark || msgs[i].querySelector(P.assistantMark)) { target = msgs[i]; break; }
    }
    if (!target) return false;
    let parsed;
    try {
      parsed = A.makeAssistant(target, P);
    } catch (e) {
      return false;   // 解析异常时宁可不动，也不要误触发重新生成
    }
    const blocks = (parsed && parsed.blocks) || [];
    // 没有思考块就谈不上「只剩思考、正文为空」，避免对纯空消息误判
    const hasThinking = blocks.some(function (b) { return b && b.type === 'thinking'; });
    if (!hasThinking) return false;
    // 只看有没有「实质内容」：thinking 块是过程，不算输出
    return !blocks.some(function (b) { return b && b.type !== 'thinking'; });
  };

  /**
   * 判断页面是否显示「服务器暂时不可用」——风控的第三种形态。
   *
   * 与另两种的区别：它不是写在消息正文里，而是消息下方的状态提示，
   * 与按钮组排在一起。故必须排除正文区域（.ds-markdown），
   * 否则 AI 自己在回答里讲到这个词也会被误判成风控。
   *
   * 判定方式：在消息容器内找含该文本、且不在 markdown 正文里的元素。
   * 文本匹配而非类名匹配，是因为站点的状态类名带哈希、会随版本变化。
   *
   * @returns {boolean} 是否显示服务器不可用
   */
  A.isServerUnavailable = function () {
    const P = A.activeProfile();
    const msgs = document.querySelectorAll(P.item || '.ds-message');
    if (!msgs.length) return false;
    // 往前看最近三条：风控停止时该提示可能挂在倒数第二条附近，
    // 且最后一条可能被解析成用户消息。只查最后一条会漏。
    const start = Math.max(0, msgs.length - 3);
    for (let i = start; i < msgs.length; i++) {
      const nodes = msgs[i].querySelectorAll('span, div');
      for (let j = 0; j < nodes.length; j++) {
        const n = nodes[j];
        // 精确匹配该短语，且必须不在正文里——正文里出现是在描述这个话题，不是状态
        if (n.textContent.indexOf('服务器暂时不可用') >= 0 && !n.closest('.ds-markdown')) {
          return true;
        }
      }
    }
    return false;
  };

  /**
   * 判断页面是否显示「消息发送过于频繁」——第四种风控形态。
   *
   * 与其它三种的区别：它对应的恢复动作是 `/reai1`（消息频繁失败后重发），
   * 而不是 `/reai`（重新生成）。选错指令会无效。
   *
   * 位置特征：与「服务器暂时不可用」一样，是消息下方的状态提示，不在正文里。
   *
   * @returns {boolean} 是否显示发送过于频繁
   */
  A.isRateLimited = function () {
    const P = A.activeProfile();
    if (!P) return false;
    const msgs = document.querySelectorAll(P.item || '.ds-message');
    if (!msgs.length) return false;
    const start = Math.max(0, msgs.length - 3);
    for (let i = start; i < msgs.length; i++) {
      const nodes = msgs[i].querySelectorAll('span, div');
      for (let j = 0; j < nodes.length; j++) {
        const n = nodes[j];
        if (n.textContent.indexOf('消息发送过于频繁') >= 0 && !n.closest('.ds-markdown')) {
          return true;
        }
      }
    }
    return false;
  };

  // 连续限流计数：连续两次限流即停止自动恢复。
  //
  // 为什么：限流意味着服务端已经在拒绝请求，此时继续自动重发只会加剧限流、
  // 甚至延长封禁时间。连续两次说明不是偶发，应立即停手交给人判断。
  let rateLimitStreak = 0;

  /**
   * 处理限流形态：连续两次即停手，否则延迟后用重发指令恢复。
   *
   * 抽成独立函数的原因：这段逻辑分支较多，内联会把 recoverIfStopped 撑破行数上限。
   *
   * 为什么连续两次要停：限流意味着服务端已在拒绝请求，此时继续自动重发
   * 只会加剧限流、延长封禁时间。连续两次说明不是偶发，应立即停手交给人判断。
   */
  function tryRecoverRateLimit() {
    rateLimitStreak += 1;
    A.log && A.log('[风控恢复] 检测到限流（消息发送过于频繁），连续第 ' + rateLimitStreak + ' 次');
    if (rateLimitStreak >= 2) {
      A.log && A.log('[风控恢复] 连续两次限流，停止自动恢复，等待人工处理');
      rateLimitStreak = 0;
      return;
    }
    const P = A.activeProfile();
    const retryExpr = P && P.retrySendExpr;
    if (!retryExpr) {
      A.warn('检测到限流，但站点未配置重发表达式，无法自动恢复');
      return;
    }
    recovering = true;
    A.log && A.log('[风控恢复] ' + (RECOVER_DELAY_MS / 1000) + ' 秒后用重发指令恢复');
    setTimeout(function () {
      A.execClick(retryExpr, 'unique', function (ok, reason) {
        recovering = false;
        if (ok) A.log && A.log('[风控恢复] 重发已触发');
        else A.warn('[风控恢复] 重发失败：' + (reason || '未知原因'));
      });
    }, RECOVER_DELAY_MS);
  }

  /**
   * 检测到异常停止后延迟点一次「重新生成」。
   *
   * 由生成态轮询在「生成中 → 空闲」翻转时调用（见 04_observer.js）。
   * 覆盖两种风控形态：「已停止」显式提示、输出为空。二者恢复动作相同。
   * 正常生成结束不受影响——那时末条有正文，两个判定都不成立。
   */
  A.recoverIfStopped = function () {
    // 开关关闭时完全不介入：这是侵入性动作，必须由用户显式开启。
    //
    // 曾为「避免噪音」而不在此记日志，结果实机排查时连「函数有没有被调用」
    // 都无从判断——静默是排查的最大障碍。现改为：只有确实存在停止形态时
    // 才记一条「因开关关闭跳过」，正常生成结束不留痕，兼顾可查与不刷屏。
    if (!autoRecoverEnabled) {
      if (A.isStoppedByRisk() || A.isServerUnavailable() || A.isEmptyByRisk()) {
        A.log && A.log('[风控恢复] 检测到停止形态，但开关未开启，跳过');
      }
      return;
    }
    if (recovering) {
      A.log && A.log('[风控恢复] 上一轮恢复仍在进行，跳过本轮');
      return;
    }
    // 先看用户是否已向上翻看历史：在底部才考虑恢复。
    //
    // 为什么加这一道：用户手动点停止也会出现「已停止」，那种情况绝不能替他重新生成——
    // 他是主动不要这条回复的。而「往上翻看历史」是一个可观测的信号：
    // 主动停止后用户常会回翻对话找上下文，此刻不打扰他，比替他重跑更稳妥。
    //
    // 这道判断的局限要说清楚：滚动位置与「谁点了停止」并无因果关系，
    // 它只能降低误触发概率，不能精确区分「用户停的」与「风控掐的」。
    // 代价是用户恰好往上翻时真遇风控，那次不会自动恢复——我们选择宁可漏恢复，
    // 也不在用户主动停止后擅自重跑。
    //
    // 站点未配置 scrollToBottomButton 时 isAtBottom 恒为 false，即永不自动恢复；
    // 这是保守取向：判定缺失时宁可不动作。
    if (!A.isAtBottom || !A.isAtBottom()) {
      // 记下来：这是「该恢复却没恢复」最常见的原因，此前静默返回导致无从排查
      A.log && A.log('[风控恢复] 判定不在底部，跳过（用户可能正在翻看历史）');
      return;
    }
    // 先判限流：它走另一条恢复指令，且连续两次要停手。实现见 tryRecoverRateLimit。
    if (A.isRateLimited()) {
      tryRecoverRateLimit();
      return;
    }
    // 走到这里说明本轮不是限流，清零连续计数（限流要求「连续」两次）
    rateLimitStreak = 0;

    // 其余形态任一成立都要恢复。按代价从低到高依次判，前一个成立就不再往后算。
    //
    // 注意这里的写法约束：形态**可能同时出现**（截图实测过「服务器暂时不可用」
    // 与「已停止」并存）。必须保证无论如何只执行一次恢复动作，不能写成多个独立 if，
    // 否则同一次停止会被点多次。下面用短路赋值保证只有一个成立，末尾统一走一次恢复。
    //   1) 已停止       —— 读标题栏文字，最便宜
    //   2) 服务器不可用  —— 查状态提示，中等
    //   3) 输出为空      —— 要跑一次完整解析，最贵，放最后
    const stopped = A.isStoppedByRisk();
    const unavailable = stopped ? false : A.isServerUnavailable();
    const empty = (stopped || unavailable) ? false : A.isEmptyByRisk();
    // 都没命中也要记：这说明本次是正常生成结束，或出现了尚未覆盖的形态。
    // 记成日志后，下次「该恢复却没恢复」时能直接看出是没识别到形态。
    if (!stopped && !unavailable && !empty) {
      A.log && A.log('[风控恢复] 未识别到停止形态（已停止/服务器不可用/输出为空 均不成立）');
      return;
    }
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

  // 加载完成探针：列出实际挂上的函数名，一眼确认有没有挂成。
  console.log('[AI-Mirror][content] [风控恢复] 模块加载完成，已挂载：'
    + ['recoverIfStopped', 'isStoppedByRisk', 'isServerUnavailable', 'isRateLimited', 'isEmptyByRisk']
      .filter(function (n) { return typeof A[n] === 'function'; }).join(','));
})();
