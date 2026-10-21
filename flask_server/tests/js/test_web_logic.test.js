/* ============================================================
 * 前端纯逻辑测试（node 自带测试运行器）
 *
 * 背景：
 *   web_page.js 与 DOM / fetch 强耦合，无法脱离浏览器测试，前端逻辑
 *   此前没有任何回归安全网。把纯逻辑抽到 web_logic.js 后，可用 node
 *   直接断言，无需浏览器。
 *
 * 运行方式：
 *   node --test flask_server/tests/js/
 *   （或指定本文件：node --test test_web_logic.test.js）
 *
 * 覆盖：失败分类（超时 / 网络错 / 其它）、离线标记、断开容差、慢响应判定。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// 被测模块：与浏览器共用同一份 web_logic.js
const logic = require(path.join(__dirname, '..', '..', 'web_bridge', 'web_logic.js'));

test('失败分类：AbortError 归为超时（已发出无响应）', () => {
  assert.strictEqual(logic.classifyFailKind('AbortError', ''), 'timeout(已发出,无响应)');
});

test('失败分类：TypeError 归为网络错（未发出）', () => {
  assert.strictEqual(logic.classifyFailKind('TypeError', ''), 'neterr(未发出/断连)');
});

test('失败分类：其它错误取消息前 40 字', () => {
  const msg = 'x'.repeat(100);
  const got = logic.classifyFailKind('Error', msg);
  assert.strictEqual(got.length, 40);
  assert.strictEqual(got, msg.slice(0, 40));
});

test('失败分类：无名无消息回退 unknown', () => {
  assert.strictEqual(logic.classifyFailKind('', ''), 'unknown');
});

test('离线标记：断网时带 OFFLINE', () => {
  assert.strictEqual(logic.offlineSuffix(false), ' OFFLINE');
});

test('离线标记：在线时为空', () => {
  assert.strictEqual(logic.offlineSuffix(true), '');
});

test('断开判定：未达容差不显示断开', () => {
  assert.strictEqual(logic.shouldShowDisconnected(3, 4), false);
});

test('断开判定：达到容差显示断开', () => {
  assert.strictEqual(logic.shouldShowDisconnected(4, 4), true);
  assert.strictEqual(logic.shouldShowDisconnected(5, 4), true);
});

test('慢响应：低于阈值不算慢', () => {
  assert.strictEqual(logic.isSlowPoll(999, 1000), false);
});

test('慢响应：达到阈值算慢', () => {
  assert.strictEqual(logic.isSlowPoll(1000, 1000), true);
});

test('跳过判定：上一轮仍在进行时跳过', () => {
  assert.strictEqual(logic.shouldSkipPoll(true), true);
});

test('跳过判定：上一轮已结束时正常发起', () => {
  assert.strictEqual(logic.shouldSkipPoll(false), false);
});

test('跳过判定：未初始化时视为空闲', () => {
  // pollBusy 未赋值时为 undefined，不应被当成忙碌
  assert.strictEqual(logic.shouldSkipPoll(undefined), false);
});

test('中止判定：AbortError 算主动中止', () => {
  assert.strictEqual(logic.isAbortError('AbortError'), true);
});

test('中止判定：其它错误不算主动中止', () => {
  assert.strictEqual(logic.isAbortError('TypeError'), false);
});

test('中止判定：未提供错误名时不算主动中止', () => {
  assert.strictEqual(logic.isAbortError(undefined), false);
});

test('重载判定：停留超过阈值需重载', () => {
  assert.strictEqual(logic.shouldReloadAfterHidden(31000, 30000), true);
});

test('重载判定：停留未超阈值不重载', () => {
  assert.strictEqual(logic.shouldReloadAfterHidden(29000, 30000), false);
});

test('重载判定：恰好等于阈值不重载', () => {
  assert.strictEqual(logic.shouldReloadAfterHidden(30000, 30000), false);
});

test('重载判定：未记录切后台时刻时不重载', () => {
  assert.strictEqual(logic.shouldReloadAfterHidden(0, 30000), false);
});

test('重载判定：时间回拨导致的负值不重载', () => {
  assert.strictEqual(logic.shouldReloadAfterHidden(-5000, 30000), false);
});

test('可发送判定：有文字可发', () => {
  assert.strictEqual(logic.canSend('hello', 0), true);
});

test('可发送判定：只有图片也可发', () => {
  assert.strictEqual(logic.canSend('', 1), true);
});

test('可发送判定：文字与图片都有可发', () => {
  assert.strictEqual(logic.canSend('hi', 2), true);
});

test('可发送判定：两者都为空不发', () => {
  assert.strictEqual(logic.canSend('', 0), false);
});

test('可发送判定：纯空白文字视为空', () => {
  // 空格与换行经 trim 后为空，不应被当成有内容
  assert.strictEqual(logic.canSend('   \n\t ', 0), false);
});

test('可发送判定：非法图片数按 0 处理', () => {
  assert.strictEqual(logic.canSend('', undefined), false);
  assert.strictEqual(logic.canSend('', null), false);
});

test('可发送判定：文字为 null 时按空处理', () => {
  assert.strictEqual(logic.canSend(null, 0), false);
  assert.strictEqual(logic.canSend(null, 1), true);
});

test('发送成功判定：ok 为真算成功', () => {
  assert.strictEqual(logic.isSendOk({ ok: true, status: 200 }), true);
});

test('发送成功判定：ok 为假算失败', () => {
  assert.strictEqual(logic.isSendOk({ ok: false, status: 500 }), false);
});

test('发送成功判定：无响应对象算失败', () => {
  // 网络层抛错时没有响应对象
  assert.strictEqual(logic.isSendOk(null), false);
  assert.strictEqual(logic.isSendOk(undefined), false);
});

test('发送失败分类：有响应时按 HTTP 状态码', () => {
  assert.strictEqual(logic.sendFailKind({ status: 500 }, '', ''), 'http500');
  assert.strictEqual(logic.sendFailKind({ status: 413 }, '', ''), 'http413');
});

test('发送失败分类：无响应时按异常类型', () => {
  assert.strictEqual(logic.sendFailKind(null, 'AbortError', ''), 'timeout(已发出,无响应)');
  assert.strictEqual(logic.sendFailKind(null, 'TypeError', ''), 'neterr(未发出/断连)');
});

test('发送失败分类：无响应且无异常名时回退 unknown', () => {
  assert.strictEqual(logic.sendFailKind(null, '', ''), 'unknown');
});

test('自动播放拦截：NotAllowedError 算被拦截', () => {
  assert.strictEqual(logic.isAutoPlayBlocked('NotAllowedError'), true);
});

test('自动播放拦截：数字错误码 11 算被拦截', () => {
  assert.strictEqual(logic.isAutoPlayBlocked(11), true);
  // 部分浏览器把 code 序列化成字符串
  assert.strictEqual(logic.isAutoPlayBlocked('11'), true);
});

test('自动播放拦截：其它错误不算被拦截', () => {
  assert.strictEqual(logic.isAutoPlayBlocked('NotSupportedError'), false);
  assert.strictEqual(logic.isAutoPlayBlocked(''), false);
  assert.strictEqual(logic.isAutoPlayBlocked(undefined), false);
});

test('语音重试判定：未达上限且非拦截时应重试', () => {
  assert.strictEqual(logic.shouldRetryVoice('NotSupportedError', 0, 2), true);
  assert.strictEqual(logic.shouldRetryVoice('NotSupportedError', 1, 2), true);
});

test('语音重试判定：达到上限不再重试', () => {
  assert.strictEqual(logic.shouldRetryVoice('NotSupportedError', 2, 2), false);
  assert.strictEqual(logic.shouldRetryVoice('NotSupportedError', 5, 2), false);
});

test('语音重试判定：被浏览器拦截时绝不重试', () => {
  // 即使还有重试次数，策略拦截也无法通过重试解决
  assert.strictEqual(logic.shouldRetryVoice('NotAllowedError', 0, 2), false);
  assert.strictEqual(logic.shouldRetryVoice(11, 0, 2), false);
});

test('语音重试判定：重试次数非法按 0 处理', () => {
  assert.strictEqual(logic.shouldRetryVoice('Error', undefined, 2), true);
  assert.strictEqual(logic.shouldRetryVoice('Error', null, 2), true);
});

test('语音失败提示：被拦截时提示手动点播放', () => {
  assert.strictEqual(logic.voiceFailText('NotAllowedError'), '请点播放键开始');
  assert.strictEqual(logic.voiceFailText(11), '请点播放键开始');
});

test('语音失败提示：其它原因提示重试', () => {
  assert.strictEqual(logic.voiceFailText('NotSupportedError'), '播放失败，请点播放键重试');
  assert.strictEqual(logic.voiceFailText(''), '播放失败，请点播放键重试');
});

test('语音就绪判定：status 为 ready 且带文件名才算就绪', () => {
  assert.strictEqual(logic.isVoiceReady({ status: 'ready', name: 'a.mp3' }), true);
});

test('语音就绪判定：缺文件名不算就绪', () => {
  // 没有文件名就构造不出有效播放地址，应继续轮询
  assert.strictEqual(logic.isVoiceReady({ status: 'ready' }), false);
  assert.strictEqual(logic.isVoiceReady({ status: 'ready', name: '' }), false);
});

test('语音就绪判定：状态不是 ready 不算就绪', () => {
  assert.strictEqual(logic.isVoiceReady({ status: 'processing', name: 'a.mp3' }), false);
});

test('语音就绪判定：响应体为空不算就绪', () => {
  assert.strictEqual(logic.isVoiceReady(null), false);
  assert.strictEqual(logic.isVoiceReady(undefined), false);
  assert.strictEqual(logic.isVoiceReady({}), false);
});
