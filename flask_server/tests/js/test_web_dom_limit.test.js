/* ============================================================
 * 网页版机器人 —— DOM 上限与向前懒加载模块的测试
 *
 * 被测文件：flask_server/web_bridge/web_dom_limit.js
 * 该模块以 IIFE 形式挂到 window.WebDom，内部持有运行时状态，
 * 且依赖 DOM 容器与 fetch。本测试用最小假对象隔离这两者，
 * 不引入任何第三方依赖，直接用 node:test 运行。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// 被测文件的绝对路径
const MOD_PATH = path.join(__dirname, '..', '..', 'web_bridge', 'web_dom_limit.js');

/**
 * 构造一个假消息节点：只需支持读取 data-seq 与测量高度。
 * @param {number} seq 消息序号
 * @returns {Object} 假节点
 */
function makeNode(seq) {
  return {
    // 只有 data-seq 属性有意义，其余属性一律返回 null
    getAttribute: (name) => (name === 'data-seq' ? String(seq) : null),
    offsetHeight: 10,
  };
}

/**
 * 构造一个假消息列表容器，模拟 children / 首尾节点 / 滚动相关属性。
 * @param {number[]} seqs 初始就位的消息序号
 * @returns {Object} 假容器
 */
function makeList(seqs) {
  const children = (seqs || []).map(makeNode);
  const el = {
    children: children,
    scrollTop: 0,          // 当前滚动位置
    scrollHeight: 1000,    // 内容总高
    clientHeight: 500,     // 可视高度
    // 挂滚动监听：记录下来供测试手动触发
    addEventListener: (type, fn) => { el._handlers[type] = fn; },
    _handlers: {},
    // 移除子节点：同步维护 children 数组
    removeChild: (node) => {
      const i = children.indexOf(node);
      if (i >= 0) children.splice(i, 1);
    },
  };
  // 首尾节点用取值器实时计算，裁剪循环每轮都能拿到当前值
  Object.defineProperty(el, 'firstChild', { get: () => children[0] || null });
  Object.defineProperty(el, 'lastChild', { get: () => children[children.length - 1] || null });
  return el;
}

/**
 * 重新加载被测模块，拿到一份全新的内部状态。
 * 模块状态是模块级的，多个用例之间必须隔离，否则相互污染。
 * @returns {Object} window.WebDom
 */
function loadFresh() {
  // 模块需要 window 存在才能挂载
  global.window = {};
  // 清掉 require 缓存，强制重新执行 IIFE，得到干净的初始状态
  delete require.cache[require.resolve(MOD_PATH)];
  require(MOD_PATH);
  return global.window.WebDom;
}

// ---------------- init 与 recompute ----------------

test('init：从已有 DOM 重算节点数与 seq 范围', () => {
  const dom = loadFresh();
  const list = makeList([3, 5, 9]);
  dom.init({ listEl: list });
  // 三个节点都应被计入
  assert.equal(dom.count(), 3);
  // 最早序号应是 3
  assert.equal(dom.minSeq(), 3);
});

test('init：容器为空时计数为零、最早序号为无穷大', () => {
  const dom = loadFresh();
  dom.init({ listEl: makeList([]) });
  assert.equal(dom.count(), 0);
  // 无节点时锚点为无穷大，表示「还不知道最早一条」
  assert.equal(dom.minSeq(), Infinity);
});

test('init：未传容器时不抛异常', () => {
  const dom = loadFresh();
  // 不传任何参数，走默认空对象分支
  dom.init();
  assert.equal(dom.count(), 0);
});

test('init：会挂上 scroll 监听', () => {
  const dom = loadFresh();
  const list = makeList([]);
  dom.init({ listEl: list });
  // 监听函数应已登记
  assert.equal(typeof list._handlers.scroll, 'function');
});

// ---------------- note 维护锚点 ----------------

test('note：登记更小的 seq 会下移锚点', () => {
  const dom = loadFresh();
  dom.init({ listEl: makeList([10]) });
  dom.note(4);
  assert.equal(dom.minSeq(), 4);
  // 计数应累加
  assert.equal(dom.count(), 2);
});

test('note：非法 seq 不计入', () => {
  const dom = loadFresh();
  dom.init({ listEl: makeList([]) });
  // 0、空串、非数字都视为无效
  dom.note(0);
  dom.note('');
  dom.note('abc');
  assert.equal(dom.count(), 0);
});

// ---------------- trim 裁剪 ----------------

test('trim newest：超过上限时从尾部删除，保留顶部最新', () => {
  const dom = loadFresh();
  // 造 55 条，超出 MAX_DOM(50) 五条
  const seqs = Array.from({ length: 55 }, (_, i) => i + 1);
  const list = makeList(seqs);
  dom.init({ listEl: list });
  dom.trim('newest');
  // 应裁到上限 50 条
  assert.equal(dom.count(), 50);
  // 保留的是前 50 条，故首条仍是 1
  assert.equal(list.firstChild.getAttribute('data-seq'), '1');
});

test('trim oldest：从头部删除并补偿滚动位置', () => {
  const dom = loadFresh();
  const seqs = Array.from({ length: 55 }, (_, i) => i + 1);
  const list = makeList(seqs);
  list.scrollTop = 500;
  dom.init({ listEl: list });
  dom.trim('oldest');
  assert.equal(dom.count(), 50);
  // 从头部删了 5 条、每条高 10，滚动位置应减少 50
  assert.equal(list.scrollTop, 450);
});

test('trim：未超上限时不删任何节点', () => {
  const dom = loadFresh();
  const list = makeList([1, 2, 3]);
  dom.init({ listEl: list });
  dom.trim('newest');
  assert.equal(dom.count(), 3);
});

test('trim：被裁掉的节点会回调 evict 反注册', () => {
  const dom = loadFresh();
  const seqs = Array.from({ length: 52 }, (_, i) => i + 1);
  const list = makeList(seqs);
  const evicted = [];
  dom.init({ listEl: list, evict: (s) => evicted.push(s) });
  dom.trim('newest');
  // 从尾部删了 2 条，应回调两次，且是最大的两个序号
  assert.deepEqual(evicted.sort((a, b) => a - b), [51, 52]);
});

test('trim：evict 回调抛错不影响裁剪', () => {
  const dom = loadFresh();
  const seqs = Array.from({ length: 52 }, (_, i) => i + 1);
  const list = makeList(seqs);
  // 回调故意抛错，裁剪仍应完成
  dom.init({ listEl: list, evict: () => { throw new Error('boom'); } });
  dom.trim('newest');
  assert.equal(dom.count(), 50);
});

// ---------------- afterAppend ----------------

test('afterAppend：停在顶部时裁掉最旧', () => {
  const dom = loadFresh();
  const seqs = Array.from({ length: 55 }, (_, i) => i + 1);
  const list = makeList(seqs);
  list.scrollTop = 0;   // 停在顶部
  dom.init({ listEl: list });
  dom.afterAppend();
  assert.equal(dom.count(), 50);
});

test('afterAppend：用户已向下翻看时不裁', () => {
  const dom = loadFresh();
  const seqs = Array.from({ length: 55 }, (_, i) => i + 1);
  const list = makeList(seqs);
  list.scrollTop = 200; // 已向下翻看
  dom.init({ listEl: list });
  dom.afterAppend();
  // 不应删除，避免正在读的内容被抽走
  assert.equal(dom.count(), 55);
});

// ---------------- onScroll 触发懒加载 ----------------

test('onScroll：接近底部时触发向前加载', async () => {
  const dom = loadFresh();
  const list = makeList([10]);
  // loadOlder 要求已注入渲染回调，否则会直接提前返回
  dom.init({ listEl: list, render: () => true });
  // 准备一个永远不返回更多数据的 fetch，仅用于观察是否被调用
  let called = 0;
  global.fetch = () => { called++; return Promise.resolve({ json: () => Promise.resolve({ success: true, messages: [] }) }); };
  // 让滚动位置贴近底部：总高 1000 - 滚动 500 - 可视 500 = 0 < 80
  list.scrollTop = 500;
  list._handlers.scroll();
  // 等待微任务链走完
  await new Promise((r) => setImmediate(r));
  assert.equal(called, 1);
});

test('onScroll：离底部还远时不触发', () => {
  const dom = loadFresh();
  const list = makeList([10]);
  dom.init({ listEl: list });
  let called = 0;
  global.fetch = () => { called++; return Promise.resolve({ json: () => Promise.resolve({ success: true, messages: [] }) }); };
  // 距底部 500 - 500 = 500，远大于阈值 80
  list.scrollTop = 0;
  list._handlers.scroll();
  assert.equal(called, 0);
});

// ---------------- loadOlder 翻页 ----------------

test('loadOlder：加载成功时按新到旧渲染，并更新 noMore', async () => {
  const dom = loadFresh();
  const list = makeList([10]);
  const rendered = [];
  dom.init({ listEl: list, render: (m) => { rendered.push(m.seq); return true; } });
  // 服务端返回两条更早的消息，且还有更多
  global.fetch = () => Promise.resolve({
    json: () => Promise.resolve({ success: true, messages: [{ seq: 8 }, { seq: 9 }], has_more: true }),
  });
  dom.loadOlder();
  await new Promise((r) => setImmediate(r));
  // 倒序处理后，先渲染 9 再渲染 8
  assert.deepEqual(rendered, [9, 8]);
});

test('loadOlder：返回空列表时置 noMore，不再重复请求', async () => {
  const dom = loadFresh();
  const list = makeList([10]);
  dom.init({ listEl: list, render: () => true });
  let called = 0;
  global.fetch = () => { called++; return Promise.resolve({ json: () => Promise.resolve({ success: true, messages: [] }) }); };
  dom.loadOlder();
  await new Promise((r) => setImmediate(r));
  // 第一次调用后 noMore 为真，第二次应直接返回
  dom.loadOlder();
  assert.equal(called, 1);
});

test('loadOlder：无最早锚点时不发起请求', () => {
  const dom = loadFresh();
  const list = makeList([]);
  dom.init({ listEl: list, render: () => true });
  let called = 0;
  global.fetch = () => { called++; return Promise.resolve({ json: () => Promise.resolve({ success: true, messages: [] }) }); };
  // 容器为空，minSeq 为无穷大，应直接返回
  dom.loadOlder();
  assert.equal(called, 0);
});

test('loadOlder：fetch 失败时记录日志且不抛异常', async () => {
  const dom = loadFresh();
  const list = makeList([10]);
  const logs = [];
  dom.init({ listEl: list, render: () => true, log: (tag, msg) => logs.push(tag + ':' + msg) });
  global.fetch = () => Promise.reject(new Error('net down'));
  dom.loadOlder();
  await new Promise((r) => setImmediate(r));
  // 应记到失败日志，且不向外抛
  assert.ok(logs.some((l) => l.startsWith('older:fail')));
});

// ---------------- MAX_DOM 常量 ----------------

test('MAX_DOM 暴露为 50', () => {
  const dom = loadFresh();
  assert.equal(dom.MAX_DOM, 50);
});
