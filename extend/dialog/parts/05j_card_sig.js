// 模块：extend/dialog/parts/05j_card_sig.js
// 用途：工具调用的「执行签名」存取与卡片状态重判。
//       签名用「会话 + 消息指纹 + 工具名 + 参数」组成，跨网页重渲染保持稳定，
//       用于刷新后恢复卡片的已执行状态、以及判断镜像里是否还存在对应调用。
//       从 05g_cards.js 抽出，使该文件保持在行数上限内。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
// 加载顺序：必须在 05g_cards.js 之后、06_execute.js 之前。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  /**
   * 计算一次工具调用的执行签名，用于跨刷新恢复「已执行」状态。
   *
   * 为什么需要它：代码块 id 是内容指纹，网页重新渲染后同一段调用会得到不同 id，
   * 只靠卡片自身状态无法跨刷新保留，刷新后卡片会退回待执行。
   * 签名改用「消息指纹 + 工具名 + 参数」，这三者在刷新后保持稳定。
   * @param {string} msgId 归属消息指纹
   * @param {Object} call 解析出的工具调用 {tool, parameters}
   * @returns {string} 命中返回签名，未命中返回空串
   */
  M._executedSig = function (msgId, call) {
    // 缺关键字段无法拼签名，直接返回空串表示「未执行过」
    if (!msgId || !call || !call.tool) {
      log('[签名诊断] 跳过：msgId=' + (msgId || '(空)') + ' tool=' + (call && call.tool));
      return '';
    }
    // 取当前会话的执行签名库
    const conv = this.ensureConv(this.activeConv);
    const store = (conv && conv.executedSigs) || {};
    // 签名键带上会话 id：消息指纹是内容摘要，相同内容的消息在不同会话里指纹相同，
    // 只用「消息指纹 + 工具 + 参数」会在跨会话时撞键，把别处执行过的调用误判成本次已执行。
    const sig = this.activeConv + '|' + msgId + '|' + call.tool + '|' + JSON.stringify(call.parameters || {});
    // 诊断：库里有多少签名、本次算出的签名是什么、是否命中
    log('[签名诊断] 查 sig=' + sig + ' 库内条数=' + Object.keys(store).length
      + ' 命中=' + !!store[sig]);
    // 命中返回签名本身，未命中返回空串
    return store[sig] ? sig : '';
  };

  /**
   * 登记一次工具调用为「已执行」，供刷新后恢复状态。
   *
   * 代码块 id 会随网页重新渲染变化，只靠卡片自身状态无法跨刷新保留，
   * 故用「消息指纹 + 工具名 + 参数」这组稳定信息作为键。
   * @param {Object} card 刚执行完的卡片
   */
  M._markExecutedSig = function (card) {
    // 缺会话、卡片、消息指纹或工具名，无法拼签名，直接放弃登记
    if (!this.activeConv || !card || !card.msgId || !card.tool) return;
    const conv = this.ensureConv(this.activeConv);
    // 签名库不存在则先建
    if (!conv.executedSigs) conv.executedSigs = {};
    // 与 _executedSig 保持同一键格式（含会话 id），否则登记与查询对不上。
    const sig = this.activeConv + '|' + card.msgId + '|' + card.tool + '|' + JSON.stringify(card.parameters || {});
    log('[签名诊断] 登记 sig=' + sig);
    // 置真即登记完成
    conv.executedSigs[sig] = true;
  };

  /**
   * 会话加载完成后，按签名库重判消息树里的卡片状态。
   *
   * 为什么需要它：签名库是从后端异步取回的，而卡片可能在取回之前就建好了。
   * 建卡时查到的签名库还是空的，卡片便被建成待执行态；此后没有任何环节
   * 回头纠正，于是刷新页面后已执行卡片一律退回待执行。
   * 本方法在加载完成时补做这一次重判，让时序先后不再影响结果。
   *
   * 只把「未执行」的卡片往「已执行」方向纠正，反向一律不动：
   * 内存里已标为执行过的，可能是本次会话刚跑完的结果，不该被旧存档覆盖。
   *
   * @param {Object} conv   会话记录；缺省取当前活动会话
   * @param {string} convId 会话标识。**必须由调用方传入**：加载会话时
   *                        `activeConv` 可能尚未切到正在加载的那个会话，
   *                        用它会拼出错误的签名前缀，导致永远命中不了。
   */
  M._restoreExecutedCards = function (conv, convId) {
    // 会话标识优先用显式传入的，其次才是当前活动会话
    const id = convId || this.activeConv;
    const c = conv || this.ensureConv(id);
    if (!c) return;
    const store = c.executedSigs || {};
    // 统计量：树内卡片总数 / 工具卡数 / 参与比对卡数 / 恢复数 / 缺字段数
    let totalCards = 0;      // 树内卡片总数
    let toolCards = 0;       // 其中工具卡片数
    let unchecked = 0;       // 参与签名比对的卡片数
    let restored = 0;        // 恢复为已执行的卡片数
    let noFields = 0;        // 缺 msgId / tool 无法比对的卡片数
    // 遍历消息树里的每个节点
    Object.keys(c.msgTree || {}).forEach((key) => {
      const node = c.msgTree[key];
      const cards = (node && node.cards) || {};
      // 遍历该节点下的每张卡片
      Object.keys(cards).forEach((cid) => {
        const card = cards[cid];
        if (!card) return;
        totalCards += 1;
        // 非工具卡不参与签名判定
        if (!card.isTool) return;
        toolCards += 1;
        // 只纠正「尚未执行」的
        if (card.executed) return;
        // 缺字段无法拼签名，单独计数以区分「数据缺失」与「签名不匹配」
        if (!card.tool || !card.msgId) { noFields += 1; return; }
        unchecked += 1;
        // 与 _executedSig 使用完全相同的键格式，否则查不到
        const sig = id + '|' + card.msgId + '|' + card.tool
          + '|' + JSON.stringify(card.parameters || {});
        if (!store[sig]) return;
        // 命中签名：纠正为已执行态并标记来源
        card.executed = true;
        card.status = 'done';
        card.restoredFromSig = true;
        restored += 1;
      });
    });
    // 汇总诊断：树内卡片数为 0 说明卡片没进树（建卡或存档环节的问题）；
    // 不为 0 但恢复为 0 说明签名对不上（指纹或参数不一致）。
    log('[卡片诊断] 重判：树内卡片=' + totalCards + ' 工具卡=' + toolCards
      + ' 待判定=' + unchecked + ' 恢复=' + restored + ' 缺字段=' + noFields
      + ' 签名库=' + Object.keys(store).length);
    if (restored) {
      log('loadConversation 重判卡片：恢复 ' + restored + ' 张已执行卡片');
    }
  };

  /**
   * 按「执行签名」判断镜像里是否还存在这张卡对应的调用。
   *
   * 为什么需要它：代码块 id 是内容指纹，AI 回复追加内容后网页重渲染，
   * 同一张卡片的 id 会变；此时按旧 id 查必然落空，卡片被误判为幽灵卡。
   * 签名由「消息指纹 + 工具名 + 参数」组成，这些在内容追加时保持不变。
   * @param {Object} card 工具卡片
   * @returns {boolean} 镜像里能找到同一调用返回 true
   */
  M.cardMatchesBySig = function (card) {
    // 缺工具名无法比对
    if (!card || !card.tool) return false;
    const messages = this.messages || [];
    const want = JSON.stringify(card.parameters || {});
    // 只按「工具名 + 参数」匹配，不掺消息指纹。
    // 消息指纹由全部块内容算出，AI 追加内容时必然改变，掺进去就等于让判据失效。
    // 参数通常含路径 / 命令等具体内容，重复概率低；即便误判为「存在」，
    // 后果也只是这张待执行卡片被执行——本就是要执行的动作，
    // 远好过误判为「不存在」导致卡片永远无法执行。
    for (let i = 0; i < messages.length; i++) {
      const blocks = window.AIMirrorDomUtils.toArray(messages[i] && messages[i].blocks);
      // 逐块检查是否为同一个工具调用
      for (let j = 0; j < blocks.length; j++) {
        const b = blocks[j];
        if (!b || b.type !== 'code') continue;
        const call = this.parseToolCall(b);
        if (!call || call.tool !== card.tool) continue;
        // 工具名相同且参数完全一致，判定镜像里仍存在
        if (JSON.stringify(call.parameters || {}) === want) return true;
      }
    }
    // 遍历完没找到，判定不存在
    return false;
  };

})();
