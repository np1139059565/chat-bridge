// 模块：extend/dialog/parts/05l_autoexec.js
// 用途：自动执行收尾（候选收集 + 决策链）与滚动轮次的放行复检。
//       _finalizeAutoExec / _collectAutoExecCandidates / _maybeAutoExecOnScroll
//       原在 05_messages.js，函数体超行数上限，抽出独立成片
//       （先例：05j_card_sig.js 之于 05g_cards.js）。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
// 加载顺序：方法挂 M 上、运行时才被调用，无硬依赖；按 05 系列惯例排在
//       06_execute.js 之前。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;
  /**
   * 收集自动执行候选：过滤本轮建出的可执行卡片，并捡起上一轮因「推送时
   * 仍在生成」被暂存的卡片。只做收集，不做执行决策。
   * @param {Object} collected _buildCardsForIncoming 的返回
   * @param {boolean} notInTree 本轮是否不入树
   * @param {boolean} generatingAtPush 推送时刻 AI 是否仍在生成
   * @returns {Object[]} runnable 候选数组（可能为空）
   */
  M._collectAutoExecCandidates = function (collected, notInTree, generatingAtPush) {
    const autoCandidates = collected.autoCandidates;
    // 4.5) 已执行卡片的处置：保持已执行态，不退回待执行。
    // 执行权只属于「本轮最后一条消息里的卡片」；一张卡片执行完成后，
    // 其执行结果就是对这次调用的最终答复，重新采集到同一代码块时沿用该结果。
    // 否则 /rall 这类刷新会重新采集历史消息，把已执行卡片重置成待执行并再跑一遍。
    const rerunCard = collected.rerunCard;
    if (rerunCard && !notInTree) {
      log('已执行卡片保持完成态：'
        + (rerunCard.tool || rerunCard.id || ''));
    }

    // 5) 自动执行：仅本轮最新的一张；不入树切片绝不自动执行。
    // 已执行过的卡片不再进候选：自动执行只针对「尚未执行」的新卡片。
    // 缺这一条时，刷新后重建的卡片若签名命中失败就会把历史卡片重跑一遍。
    // 排除 running：卡片执行期间 status='running' 但 executed 仍为 false
    //（要等 _callTool 返回才置真）。只看 executed 会让正在执行中的卡片
    // 再次进入候选、再排一次倒计时，几秒后第二次执行开始——
    // 表现为「卡片双执行、AI 收到上一张结果」。
    const runnable = autoCandidates.filter((c) => c && !c.skipped && !c.executed
      && !c.duplicate && !c._cdTimer && c.status !== 'running');
    // 捡起上一轮因「推送时仍在生成」被跳过的卡片。
    // 为什么需要：同一轮回复常被推送两次——生成中推一次（卡片建出但被跳过），
    // 生成结束再推一次；那时该消息已入树，isFreshReply 判为假，
    // 卡片不会再进候选池。若不主动捡起，它会永久停在待执行。
    // 保留「只执行会话末条」的门槛，捡起来的卡片仍要走后续 isTreeTail 判定。
    if (!generatingAtPush && this._pendingAutoExec) {
      const pending = this._pendingAutoExec;
      this._pendingAutoExec = null;
      if (pending && pending.isTool && !pending.executed && !pending.skipped
          && !pending.duplicate && !pending._cdTimer && pending.status !== 'running'
          && runnable.indexOf(pending) < 0) {
        runnable.push(pending);
        log('自动执行决策：捡起上轮因生成中跳过的卡片 id=' + (pending.id || '')
          + ' 工具=' + (pending.tool || ''));
      }
    }
    return runnable;
  };

  /**
   * 收尾：处理重复卡片重跑与「仅最新一张」的自动执行。
   * @param {Object} collected _buildCardsForIncoming 的返回
   * @param {boolean} notInTree 本轮是否不入树（不入树绝不自动执行）
   * @param {boolean} scrollOnly 是否滚动轮次
   * @param {boolean} atBottom 视口是否在底部
   * @param {boolean} generatingAtPush 推送时刻 AI 是否仍在生成。为真则一律不自动执行——
   *   此时回传会被插进正在生成的回复里，既打断输出也可能对不上位置。
   *   按既定规则：准备触发的自动执行停止、准备发出的回传丢弃，不做延迟重试。
   */
  M._finalizeAutoExec = function (collected, notInTree, scrollOnly, atBottom, generatingAtPush) {
    const autoCandidates = collected.autoCandidates;
    const runnable = this._collectAutoExecCandidates(collected, notInTree, generatingAtPush);
    // 自动执行决策留痕：这是排查「自动流程停止」的核心断点，逐条件说明为何执行/不执行。
    if (generatingAtPush) {
      log('自动执行决策：推送时 AI 仍在生成，跳过（候选=' + runnable.length + '）');
      // 暂存最新一张待执行卡片：生成结束后没有新建卡推送，不暂存就永久丢失执行机会。
      if (runnable.length) {
        this._pendingAutoExec = runnable[runnable.length - 1];
        log('自动执行决策：暂存待执行卡片 id=' + (this._pendingAutoExec.id || '')
          + ' 工具=' + (this._pendingAutoExec.tool || '') + '，等生成结束后重试');
      }
    } else if (this._convLoading && this._convLoading[this.activeConv]) {
      // 会话仍在加载：签名库尚未恢复，此时判不出「哪些已执行」，
      // 一律不自动执行，避免把历史卡片当成新卡片重跑。
      log('自动执行决策：会话仍在加载，跳过（候选=' + runnable.length + '）');
    } else if (notInTree) {
      log('自动执行决策：本轮不入树，跳过（候选=' + runnable.length + '）');
    } else if (!this.autoSendEnabled) {
      log('自动执行决策：自动开关关，跳过（候选=' + runnable.length + '）');
    } else if (!scrollOnly && runnable.length) {
      // 非滚动轮次：候选按本轮建卡顺序追加，末位即最新
      const newest = runnable[runnable.length - 1];
      // 硬门槛：卡片必须属于「会话树末条」消息。
      // 切片末条不等于会话末条——刷新后切片可能被截断或混入历史消息，
      // 末位看似最新、实则是旧消息，此时执行等于让历史卡片重跑。
      const conv = this.ensureConv(this.activeConv);
      const isTail = newest && this.isTreeTail(conv, newest.msgId);
      if (!isTail) {
        // 不 return：后面还要清 autoArmed 残留标记，中途退出会让标记留到下一轮。
        log('自动执行决策：卡片不属于会话末条，拒绝执行 id=' + (newest && newest.id)
          + ' 工具=' + (newest && newest.tool) + ' msgId=' + (newest && newest.msgId));
      } else {
        log('自动执行决策：执行最新卡片 id=' + (newest.id || '(无)')
          + ' 工具=' + (newest.tool || '(非工具)') + '（候选=' + runnable.length + '）');
        if (newest && !newest.skipped) this.scheduleExecute(newest);
      }
    } else if (scrollOnly) {
      this._maybeAutoExecOnScroll(collected.armedLast, atBottom);
    } else {
      log('自动执行决策：无候选，不执行');
    }
    // 预备标记只生效一次。
    // 除了候选池里的，还要清掉本轮建卡时被上膛、但未进池的卡片（如滚动轮次视口不在底部），
    // 否则标记残留到下一轮，历史卡片可能在后续采集里被重新认领执行。
    autoCandidates.forEach((c) => { if (c) c.autoArmed = false; });
    if (collected.armedLast) collected.armedLast.autoArmed = false;
  };

  /**
   * 滚动轮次的自动执行复检：确认「视口就停在最新处」后才放行。
   * 需三道同时成立：自动开关已开、视口在底部、上膛的是最后一条消息上的卡片
   * 且仍是待执行态（未执行 / 未跳过 / 未在倒计时）。
   * @param {Object} armedLast 上膛的最新卡片
   * @param {boolean} atBottom 视口是否在底部
   */
  M._maybeAutoExecOnScroll = function (armedLast, atBottom) {
    // status === 'pending' 已隐含排除 running（执行中状态为 'running'），
    // 故执行中的卡片不会在此被放行。若将来状态机新增中间态，须同步核对本判据。
    const armedOk = !!(armedLast && armedLast.isTool && !armedLast.executed
      && !armedLast.skipped && !armedLast.duplicate && !armedLast._cdTimer && armedLast.status === 'pending');
    // 硬门槛：上膛卡片必须属于会话树末条，否则任何滚动场景都不放行。
    // 与「切片末条」无关——切片末位在向上滚动加载历史时可能是旧消息。
    const conv = this.ensureConv(this.activeConv);
    const tailOk = !!(armedLast && this.isTreeTail(conv, armedLast.msgId));
    if (armedLast && !tailOk) {
      log('自动执行复检（滚动）：卡片不属于会话末条，拒绝 msgId=' + (armedLast.msgId || '(空)'));
    }
    // 自动开关必须纳入判定：原实现只在日志里打印了它，没参与运算，
    // 导致开关关闭时滚动路径照样执行卡片——日志写着「自动开关=false → 放行执行」，自相矛盾。
    const pass = this.autoSendEnabled && atBottom && armedOk && tailOk;
    // 自动流程是否放行的关键判定：记录四个条件与结论，便于排查「自动流程停止」。
    log('自动执行复检（滚动）：自动开关=' + this.autoSendEnabled
      + '，在底部=' + atBottom + '，末尾卡片待执行=' + armedOk
      + ' → ' + (pass ? '放行执行' : '不执行'));
    if (pass) this.scheduleExecute(armedLast);
  };

})();
