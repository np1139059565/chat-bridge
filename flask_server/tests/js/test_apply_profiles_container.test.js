/* ============================================================
 * 站点档案应用后容器选择器同步性的测试
 *
 * 被测文件：extend/content/00_state.js 中的 A.applyProfiles。
 *
 * 背景：内容脚本注入时会并发做两件事——按出厂档案初始化 currentSel、
 * 异步拉取后端档案。若初始化先完成，currentSel 会被锁定为出厂兜底档案
 * （guessProfile 找不到站点时返回 glm）的容器；后端档案随后应用成功，
 * 但若不顺手更新 currentSel，观察器就一直用错选择器重试到超时，
 * 表现为「站点配置看着正确、就是抓不到任何对话」。
 * 本测试锁定这条不变量。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// 被测模块：内容脚本共享命名空间
const STATE_PATH = path.join(__dirname, '..', '..', '..', 'extend', 'content', '00_state.js');
// 依赖模块：dom 工具（debounce / hashStr / textOf）
const DOM_UTILS_PATH = path.join(__dirname, '..', '..', '..', 'extend', 'lib', 'dom-utils.js');

/**
 * 在 node 环境下装载内容脚本模块，返回其对外命名空间。
 * @param {string} hostname 伪造的当前页面主机名
 * @returns {Object} window.AIMirrorContent
 */
function loadContent(hostname) {
  // 模块内部会读 location.hostname 猜站点
  global.location = { hostname: hostname, href: 'https://' + hostname + '/chat/abc' };
  global.window = {};
  global.document = { querySelector: () => null, querySelectorAll: () => [] };
  // 依赖：先装载 dom 工具（它自身挂到 global.AIMirrorDomUtils），
  // 再镜像一份到 window，供内容脚本按 window 取用。
  delete require.cache[require.resolve(DOM_UTILS_PATH)];
  require(DOM_UTILS_PATH);
  // dom-utils 末尾按「window 存在则挂 window」暴露接口，上面备好的
  // global.window 会直接收到 AIMirrorDomUtils，正是内容脚本读取的位置。
  delete require.cache[require.resolve(STATE_PATH)];
  require(STATE_PATH);
  return global.window.AIMirrorContent;
}

/**
 * 构造一份最小后端档案：给定站点 id 与容器选择器。
 * @param {string} pid 档案 id
 * @param {string} container 容器选择器
 * @returns {Object} 档案集
 */
function profileWith(pid, container) {
  const out = {};
  out[pid] = { label: pid, hosts: [pid + '.com'], container: container, item: '.x' };
  return out;
}

test('未登记站点：guessProfile 兜底为 glm', () => {
  const A = loadContent('unknown-site.com');
  assert.strictEqual(A.guessProfile('unknown-site.com'), 'glm');
});

test('applyProfiles：应用新档案后 currentSel 同步更新为新站点容器', () => {
  const A = loadContent('newsite.com');
  // 模拟初始化阶段先拿到的出厂选择器（错的）
  A.state.currentSel = '.glm-container';
  const ok = A.applyProfiles(profileWith('newsite', '.newsite-container'));
  assert.strictEqual(ok, true);
  // 站点被正确识别
  assert.strictEqual(A.state.profileId, 'newsite');
  // 关键不变量：容器选择器必须跟着档案一起换掉
  assert.strictEqual(A.state.currentSel, '.newsite-container');
});

test('applyProfiles：容器选择器变化且观察器在跑时触发重新探测', () => {
  const A = loadContent('newsite.com');
  A.state.currentSel = '.glm-container';
  // 模拟观察器已在运行（有容器节点）
  A.state.containerEl = { nodeType: 1 };
  let reprobeCalled = 0;
  A.reprobe = () => { reprobeCalled += 1; };
  A.applyProfiles(profileWith('newsite', '.newsite-container'));
  assert.strictEqual(reprobeCalled, 1);
});

test('applyProfiles：容器选择器未变化时不重复重新探测', () => {
  const A = loadContent('newsite.com');
  A.state.currentSel = '.same-container';
  A.state.containerEl = { nodeType: 1 };
  let reprobeCalled = 0;
  A.reprobe = () => { reprobeCalled += 1; };
  A.applyProfiles(profileWith('newsite', '.same-container'));
  assert.strictEqual(reprobeCalled, 0);
});

test('applyProfiles：观察器未运行时不做重新探测', () => {
  const A = loadContent('newsite.com');
  A.state.currentSel = '.glm-container';
  A.state.containerEl = null;
  let reprobeCalled = 0;
  A.reprobe = () => { reprobeCalled += 1; };
  A.applyProfiles(profileWith('newsite', '.newsite-container'));
  // 选择器照样要更新，只是不必重启观察器
  assert.strictEqual(A.state.currentSel, '.newsite-container');
  assert.strictEqual(reprobeCalled, 0);
});

test('applyProfiles：非法输入保持出厂兜底且不改动 currentSel', () => {
  const A = loadContent('newsite.com');
  A.state.currentSel = '.glm-container';
  assert.strictEqual(A.applyProfiles(null), false);
  assert.strictEqual(A.applyProfiles([]), false);
  assert.strictEqual(A.state.currentSel, '.glm-container');
});
