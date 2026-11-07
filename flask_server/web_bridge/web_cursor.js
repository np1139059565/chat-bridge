/* ============================================================
 * 网页版机器人 —— 游标持久化与缺口补齐
 *
 * 背景：手机端切后台超过 30 秒，回前台会整页重载（既定策略，
 * 用于丢弃陈旧 DOM、避免复用后长时间无响应）。重载后内存游标归零，
 * 首次加载走 history=1 分支，只取最新 10 条并把游标设为全局最新——
 * 后台期间积压的中间段既不在最近 10 条内，也不会被增量取到，
 * 表现为「抽屉有、手机上没出现」。
 *
 * 本模块把游标存进 localStorage：重载后读回上次进度，首屏铺屏完成后
 * 自动从该位置增量补齐，中间段不再丢失。
 *
 * 依赖注入（init）：fetchSince / renderBatch / log
 * ============================================================ */
(function () {
  'use strict';

  var KEY = 'webBotCursor';   // localStorage 键名
  var api = {};
  var deps = null;            // 注入的依赖
  var running = false;        // 防重入：一次补齐未完成不重复启动
  var lastCursor = 0;         // 模块内部记录的上次游标，供 onPollOk 比对

  /**
   * 读取上次保存的游标。
   *
   * localStorage 可能被禁用（隐私模式）或值损坏，一律退回 0，
   * 等价于「没有历史进度」，走原有首屏逻辑，不比现状更差。
   * @returns {number} 游标；无记录或非法时为 0
   */
  api.loadCursor = function () {
    try {
      var v = parseInt(localStorage.getItem(KEY), 10);
      return isNaN(v) || v < 0 ? 0 : v;
    } catch (e) {
      return 0;
    }
  };

  /**
   * 保存游标。写失败（配额满 / 被禁用）不影响主流程。
   * @param {number} v 当前游标
   */
  api.saveCursor = function (v) {
    try {
      var n = parseInt(v, 10);
      if (!isNaN(n) && n >= 0) localStorage.setItem(KEY, String(n));
    } catch (e) { /* 存储不可用：降级为不持久化 */ }
  };

  /**
   * 判断是否需要补齐：存过进度，且服务端已有更靠后的消息。
   *
   * 两条都得成立。saved 为 0 表示从未成功拉取过，此时没有「缺口」可言，
   * 按原有首屏逻辑处理即可。
   * @param {number} saved  上次保存的游标
   * @param {number} latest 服务端当前最新 seq
   * @returns {boolean} 需要补齐为 true
   */
  api.needsCatchUp = function (saved, latest) {
    var s = parseInt(saved, 10);
    var l = parseInt(latest, 10);
    if (isNaN(s) || isNaN(l)) return false;
    return s > 0 && l > s;
  };

  /**
   * 注入依赖。
   * @param {Object} d {fetchSince(cursor,limit), renderBatch(msgs), log(fn)}
   * @returns {Object} api 本身，便于链式调用
   */
  api.init = function (d) {
    deps = d || null;
    // 初始化内部游标：与实际起点保持一致，避免首轮 onPollOk 拿到 0 误判
    lastCursor = api.loadCursor();
    return api;
  };

  /**
   * 一次轮询成功后的游标维护入口。
   *
   * 只在「首次铺屏」且存在缺口时启动补齐：增量轮询本来就是接续旧的，
   * 不存在缺口。
   * @param {number}  latestSeq 本轮返回的最新 seq
   * @param {boolean} isHistory 本轮是否为首次铺屏（history=1）
   */
  api.onPollOk = function (latestSeq, isHistory) {
    var latest = parseInt(latestSeq, 10) || 0;
    if (latest <= 0) return;
    var prev = lastCursor;
    // 存在缺口：不把游标直接跳到最新，交给 run 逐批推进并按批持久化。
    // 否则补齐中途失败时，存储里已是最新值，下次重载仍会丢掉中间段。
    if (isHistory && api.needsCatchUp(prev, latest)) {
      lastCursor = latest;   // 内存记最新，避免重复触发补齐
      api.run(prev);
      return;
    }
    // 补齐进行中：游标归补齐流程维护，此处不抢先写入
    if (running) return;
    lastCursor = latest;
    api.saveCursor(latest);
  };

  /**
   * 从 fromSeq 起逐批增量拉取，直到追平服务端最新。
   *
   * 与首屏那 10 条重叠的部分由渲染侧的 seen 去重挡掉，不会重复显示。
   * 每批 200 条（接口默认上限），逐批推进游标，中间不跳过任何一条。
   * @param {number} fromSeq 起点游标
   */
  api.run = function (fromSeq) {
    if (!deps || running) return;
    var start = parseInt(fromSeq, 10);
    if (isNaN(start) || start <= 0) return;
    running = true;
    var guard = 0;   // 批次上限，防止服务端游标异常导致死循环

    /**
     * 拉取一批并决定是否继续。
     * @param {number} cur 本批起点游标
     */
    function step(cur) {
      // 50 批 × 200 条 = 1 万条，远超实际需要，仅作死循环兜底
      if (guard++ > 50) {
        running = false;
        if (deps.log) deps.log('catchup', '达到批次上限，停止');
        return;
      }
      deps.fetchSince(cur, 200).then(function (data) {
        if (!data || !data.success) {
          running = false;
          return;
        }
        var msgs = data.messages || [];
        if (msgs.length) deps.renderBatch(msgs);
        var next = parseInt(data.seq, 10) || cur;
        lastCursor = next;
        api.saveCursor(next);
        // 本批有货且游标确有推进 → 还有后续，继续；否则视为已追平
        if (msgs.length && next > cur) {
          step(next);
        } else {
          running = false;
          if (deps.log) deps.log('catchup', '补齐完成，游标=' + next);
        }
      }).catch(function (e) {
        running = false;
        if (deps.log) deps.log('catchup', '补齐失败：' + (e && e.message));
      });
    }

    if (deps.log) deps.log('catchup', '从 ' + start + ' 开始补齐');
    step(start);
  };

  /**
   * 与页面对接的一步到位封装：注入取数、渲染、日志三个依赖。
   *
   * 抽到本模块而非留在 web_page.js，是为了让主文件保持在行数阈值内；
   * 对接细节（接口地址、插入位置、去重）都属于游标补齐的职责。
   * @param {Object} page {renderMessage, clientLog, WebDom}
   */
  api.wirePage = function (page) {
    var p = page || {};
    api.init({
      // 按游标取一批增量：不传 history，走后端 list_since 分支
      fetchSince: function (cur, limit) {
        var u = '/api/web/messages?cursor=' + cur + '&limit=' + limit;
        return fetch(u, { headers: { 'Accept': 'application/json' } }).then(function (r) { return r.json(); });
      },
      // 补齐的消息比首屏那批更旧：插到列表末尾（倒序布局下即时间更早的位置）
      renderBatch: function (msgs) {
        if (!p.renderMessage) return;
        msgs.forEach(function (m) { p.renderMessage(m, true, true); });
        if (p.WebDom) p.WebDom.afterAppend();
      },
      log: p.clientLog,
    });
  };

  // 浏览器通过 window.WebCursor 使用；node 下供测试注入
  window.WebCursor = api;
})();
