// 模块：extend/content/03d_snapshot_retry.js
// 用途：结构化对话快照采集为空时的递增复查，等待会话切换后 DOM 异步挂载完成。
// 依赖：content/00_state.js（A.state / A.log）、content/03_bridge.js（A.sendPage，运行期调用）

(function () {
  'use strict';
  const A = window.AIMirrorContent;

  // 复查间隔（毫秒）：越早越密，覆盖 SPA 快渲染与慢渲染两种情形。
  // 四轮累计约 5.9 秒，用尽后放弃本轮，由后续 mutation 或滚动重新排程。
  const RETRY_DELAYS = [300, 800, 1600, 3200];

  /**
   * 空快照时同步会话身份到抽屉。
   * 抽屉靠 page_blocks 里的 conversationId 切换会话，空切片由 ingestMessages 直接忽略，
   * 不清空已有镜像。故切换瞬间即便内容尚未挂载，也要发一条只含身份的轻量切片，
   * 否则抽屉会停在上一会话，直到复查拿到非空快照才纠正。
   * @param {string} convId 当前会话 id
   * @param {string} reason 触发来源标签
   */
  A.postEmptyConvSync = function (convId, reason) {
    A.post({
      type: 'page_blocks',
      messages: [],
      page_url: location.href,
      siteKey: A.state.siteKey,
      profileId: A.state.profileId,
      conversationId: convId,
      conversationTitle: A.getConversationTitle(),
      reason: reason,
      atBottom: A.isAtBottom(),
      isGenerating: !!A.state.isGenerating
    });
  };

  /**
   * 空快照统一入口：必要时补发会话身份，再排递增复查。
   * 会话切换监听在调用 sendPage 前已写入 currentConvId 以防轮询重复触发，
   * 故身份同步不能靠 convChanged，改以「上一次实际推给抽屉的会话」为准；
   * 同步后即记下会话，避免四轮复查每轮重复发空切片。
   * @param {string} convId 当前会话 id
   * @param {string} reason 触发来源标签
   */
  A.onEmptySnapshot = function (convId, reason) {
    const syncNeeded = !!convId && convId !== A.state.lastPageConvId;
    if (syncNeeded) {
      A.postEmptyConvSync(convId, reason || 'switch');
      A.state.lastPageConvId = convId;
    }
    A.scheduleEmptyRetry(convId, reason || 'manual');
  };

  /**
   * 取消未完成的空快照复查。
   * 采到非空快照、面板关闭或会话切走时调用，避免过期定时器继续触发推送。
   */
  A.cancelEmptyRetry = function () {
    // 清掉排队中的定时器，并复位会话与轮次，使下一次空采集从头开始排程。
    if (A.state.emptyRetryTimer) {
      clearTimeout(A.state.emptyRetryTimer);
      A.state.emptyRetryTimer = null;
    }
    A.state.emptyRetryConvId = '';
    A.state.emptyRetryIdx = 0;
  };

  /**
   * 安排空快照的递增复查。
   * 同一会话已有复查排队时直接返回，让既有序列继续；换会话时旧序列作废、从头开始。
   * 复查到期后由 sendPage 重新采集：拿到非空会自行取消复查，仍为空则续跑下一轮。
   * @param {string} convId 触发空快照时的会话 id
   * @param {string} reason 触发来源标签，复查沿用以便控制台日志对齐
   */
  A.scheduleEmptyRetry = function (convId, reason) {
    // 排队中且会话未变：不重复排程，也不重置已走过的轮次。
    if (A.state.emptyRetryTimer && A.state.emptyRetryConvId === convId) return;
    // 排队中但会话已变：丢弃旧定时器，序列从第一轮重来。
    if (A.state.emptyRetryTimer) {
      clearTimeout(A.state.emptyRetryTimer);
      A.state.emptyRetryTimer = null;
    }
    // 定时器已到期（复查回调正在跑）且会话变了，同样从头开始。
    if (A.state.emptyRetryConvId !== convId) A.state.emptyRetryIdx = 0;
    A.state.emptyRetryConvId = convId;
    A.runEmptyRetry(reason);
  };

  /**
   * 执行一轮复查排程：到期时校验会话与面板状态，再强制重推一次快照。
   * 用尽轮次即放弃，避免对确实为空的新会话无限轮询。
   * @param {string} reason 触发来源标签
   */
  A.runEmptyRetry = function (reason) {
    const idx = A.state.emptyRetryIdx;
    // 轮次用尽：只记一条日志，不推送空快照。
    if (idx >= RETRY_DELAYS.length) {
      A.log && A.log('sendPage: 空快照复查用尽，放弃本轮 会话=' + A.state.emptyRetryConvId);
      A.cancelEmptyRetry();
      return;
    }
    A.state.emptyRetryTimer = setTimeout(function () {
      // 定时器已消费：置空，让 sendPage 内部的续跑判定能识别「正在复查」。
      A.state.emptyRetryTimer = null;
      // 面板关闭、会话已切走或容器正在重绑：本轮作废，由切换与重绑流程重新排程。
      if (!A.state.active || !A.state.containerEl
          || A.getConversationId() !== A.state.emptyRetryConvId) {
        A.cancelEmptyRetry();
        return;
      }
      // 轮次递增后再强制重推：仍为空时 sendPage 会带着保留的 idx 续跑。
      A.state.emptyRetryIdx += 1;
      A.sendPage(true, reason);
    }, RETRY_DELAYS[idx]);
  };
})();
