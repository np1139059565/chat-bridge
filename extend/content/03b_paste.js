// 模块：extend/content/03b_paste.js
// 用途：回传粘贴守卫——AI 生成期间挂起回传（文本/附件/回车），空闲或超时后统一冲刷。
// 来源：自 03_bridge.js 拆出（2026-11-08：原文件 489 行超出仓库 450 行上限，hygiene/quality 拦截）。
// 同挂 window.AIMirrorContent 命名空间；在 03_bridge.js 之后、04_observer.js 之前载入，
// 守卫仅运行期被调用（A.log/A.post 等跨文件引用届时已就绪），拆分不改变行为。

(function () {
  'use strict';

  const A = window.AIMirrorContent;

  // ===== 回传粘贴守卫：AI 生成期间挂起回传，空闲后统一冲刷 =====
  // 背景：工具结果回传（文本/图片/文件）与网页 AI 生成之间没有互斥。若 AI 正在逐字
  // 输出，此时写输入框并回车，会把结果插进 AI 的输出流——表现为输出中断、内容错乱。
  // 做法：两道守卫——写值/贴文件前查一次；回车前再查一次（贴文件链路长达数秒，
  // 途中 AI 可能开始生成，只查入口拦不住）。命中即把条目挂入 _pendingPaste，
  // 由按钮翻转回调（'flip'，主路径）或 1 秒轮询（'poll'，兜底）在空闲后统一冲刷；
  // 挂起超过 PASTE_SUSPEND_MAX_MS 放弃并如实上报，不无限拖。
  A._pendingPaste = [];
  // 挂起最长等待，超时如实放弃。原 30s：而网页 AI 一次正常生成常超 30s（长回答、
  // 深度研究可达数分钟），会把生成期间正常挂起的回传误判放弃。放宽到 120s：
  // 正常生成结束后照常冲刷发出；只有生成态误判卡死才会拖到放弃，放弃后卡片
  // 可「重新执行」补救。
  A.PASTE_SUSPEND_MAX_MS = 120000;

  /** 挂起一条回传。kind：'text'（未写值，冲刷时整体重放）/ 
   * 'files'（未贴文件，冲刷时整体重放）/ 
   * 'enter_only'（值或附件已就位，只欠回车——冲刷时只补回车，
   * 整体重放会把附件重复贴一遍）。 */
  A._suspendPaste = function (entry) {
    entry.suspendAt = entry.suspendAt || Date.now();
    A._pendingPaste.push(entry);
    A.log('[回传守卫] AI 生成中，回传挂起：' + entry.label);
    if (!A._pasteFlushTimer) {
      A._pasteFlushTimer = setInterval(function () {
        A._flushPendingPaste('poll');
      }, 1000);
    }
  };

  /** 冲刷挂起队列：仍在生成则继续等；空闲则取出全部逐条执行。
   * 队列空时自清定时器；翻转为主、轮询兜底（防翻转被错过）。
   * 超时清收先于生成态门：isGenerating 一旦误判卡死（站点类名把「输入框有
   * 多行内容」误判成生成中，见 2026-11-08 GLM m-three-row 事故），这道门会
   * 永久挡住冲刷，超时分支若放在门后就成了永远走不到的死代码——enter_only
   * 条目无限搁浅，文本滞留输入框无法发出。故到期条目无论状态是否空闲，
   * 都先如实放弃上报；未到期条目再按生成态门等待。 */
  A._flushPendingPaste = function (why) {
    if (!A._pendingPaste.length) {
      if (A._pasteFlushTimer) { clearInterval(A._pasteFlushTimer); A._pasteFlushTimer = null; }
      return;
    }
    const now = Date.now();
    const expired = [];
    const keep = [];
    for (let i = 0; i < A._pendingPaste.length; i++) {
      ((now - A._pendingPaste[i].suspendAt > A.PASTE_SUSPEND_MAX_MS) ? expired : keep)
        .push(A._pendingPaste[i]);
    }
    if (expired.length) {
      A._pendingPaste = keep;
      for (let i = 0; i < expired.length; i++) {
        // 如实上报放弃：dialog 侧按失败处理，卡片状态不会被假成功污染，
        // 可用「重新执行」补救。
        A.post({ type: 'auto_send_result', ok: false,
          msg: '回传放弃：挂起超过 ' + Math.round(A.PASTE_SUSPEND_MAX_MS / 1000) + 's 未能冲刷'
            + '（生成态未恢复，疑似状态误判；' + expired[i].label + '）' });
      }
      if (!keep.length) {
        if (A._pasteFlushTimer) { clearInterval(A._pasteFlushTimer); A._pasteFlushTimer = null; }
        return;
      }
    }
    if (A.state.isGenerating) return; // 仍在生成：继续挂起（到期清收已在上面完成）

    const list = A._pendingPaste.splice(0); // 空闲：取出全部，逐条执行
    A.log('[回传守卫] 空闲（' + why + '），冲刷挂起回传 ' + list.length + ' 条');
    for (let i = 0; i < list.length; i++) {
      const e = list[i];
      if (e.kind === 'text') {
        A.pasteToWebpageAI(e.text, e.autoSend);
      } else if (e.kind === 'files') {
        A._pasteFilesToWebpageAI(e.files, e.text, e.label);
      } else {
        // enter_only：只补回车。输入框可能已被站点/用户清空，此时回车无意义，如实放弃
        const ta2 = A.findInputBox();
        if (!ta2 || !ta2.value) {
          A.post({ type: 'auto_send_result', ok: false, msg: '回传放弃：挂起期间输入框已空，无法补发（' + e.label + '）' });
        } else {
          A.pressEnter(ta2);
        }
      }
    }
  };

})();
