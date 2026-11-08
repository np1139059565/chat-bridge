/* ============================================================
 * 输入框写值分流的测试
 *
 * 被测：extend/content/03_bridge.js 的 A.writeInputValue / A.isRichEditor。
 *
 * 背景：原实现一律走 HTMLTextAreaElement.prototype 的 value setter。
 * 千问（Slate）与元宝（Quill）的输入框都是 contenteditable div，没有 value
 * 属性，setter 直接抛 Illegal invocation，输入框保持为空、发送按钮不解禁，
 * 表现为「根本没办法输入」。contenteditable 唯一可靠路径是派发 paste 事件。
 * 本测试锁定按元素类型分流这条不变量。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// 被测文件：内容脚本的桥接分片与富文本编辑器分片
const BRIDGE_PATH = path.join(__dirname, '..', '..', '..', 'extend', 'content', '03_bridge.js');
const RICH_PATH = path.join(__dirname, '..', '..', '..', 'extend', 'content', '03c_rich_editor.js');
// 依赖：内容脚本共享命名空间
const STATE_PATH = path.join(__dirname, '..', '..', '..', 'extend', 'content', '00_state.js');
// 依赖：dom 工具
const DOM_UTILS_PATH = path.join(__dirname, '..', '..', '..', 'extend', 'lib', 'dom-utils.js');

/**
 * 装载内容脚本桥接分片，返回共享命名空间。
 * @returns {Object} window.AIMirrorContent
 */
function loadBridge() {
  global.location = { hostname: 'example.com', href: 'https://example.com/chat/1' };
  global.window = {};
  global.document = { querySelector: () => null, querySelectorAll: () => [], execCommand: () => true };
  delete require.cache[require.resolve(DOM_UTILS_PATH)];
  require(DOM_UTILS_PATH);
  delete require.cache[require.resolve(STATE_PATH)];
  require(STATE_PATH);
  const A = global.window.AIMirrorContent;
  // 富文本函数已拆到 03c，先装载它（与 manifest 的加载顺序一致）
  delete require.cache[require.resolve(RICH_PATH)];
  require(RICH_PATH);
  delete require.cache[require.resolve(BRIDGE_PATH)];
  require(BRIDGE_PATH);
  return A;
}

/**
 * 构造一个假 contenteditable 元素，记录 paste 是否被派发。
 * @returns {Object} 假元素，带 __pasteCount 与 __lastPasteText
 */
function fakeEditable() {
  const el = {
    nodeType: 1,
    textContent: '',
    __pasteCount: 0,
    __lastPasteText: null,
    getAttribute: function (name) { return name === 'contenteditable' ? 'true' : null; },
    focus: function () {},
    dispatchEvent: function (ev) {
      if (ev && ev.type === 'paste') {
        el.__pasteCount += 1;
        el.__lastPasteText = ev.clipboardData ? ev.clipboardData.getData('text/plain') : null;
      }
      return true;
    },
  };
  return el;
}

// DataTransfer / ClipboardEvent 在 node 环境不存在，提供最小替身
class FakeDataTransfer {
  constructor() { this._data = {}; }
  setData(type, val) { this._data[type] = val; }
  getData(type) { return this._data[type] || ''; }
}
class FakeClipboardEvent {
  constructor(type, init) {
    this.type = type;
    this.clipboardData = init && init.clipboardData;
    this.bubbles = !!(init && init.bubbles);
    this.cancelable = !!(init && init.cancelable);
  }
}

test('isRichEditor：contenteditable=true 判为富文本', () => {
  const A = loadBridge();
  assert.strictEqual(A.isRichEditor(fakeEditable()), true);
});

test('isRichEditor：普通元素判为非富文本', () => {
  const A = loadBridge();
  assert.strictEqual(A.isRichEditor({ nodeType: 1, getAttribute: () => null }), false);
  assert.strictEqual(A.isRichEditor(null), false);
  assert.strictEqual(A.isRichEditor({ nodeType: 3 }), false);
});

test('writeInputValue：富文本编辑器走 paste 事件而非 value setter', () => {
  global.DataTransfer = FakeDataTransfer;
  global.ClipboardEvent = FakeClipboardEvent;
  const A = loadBridge();
  const ed = fakeEditable();
  const ok = A.writeInputValue(ed, '你好元宝');
  assert.strictEqual(ok, true);
  assert.strictEqual(ed.__pasteCount, 1);
  assert.strictEqual(ed.__lastPasteText, '你好元宝');
});

test('writeInputValue：空文本同样派发 paste（清空场景需要）', () => {
  global.DataTransfer = FakeDataTransfer;
  global.ClipboardEvent = FakeClipboardEvent;
  const A = loadBridge();
  const ed = fakeEditable();
  A.writeInputValue(ed, '');
  assert.strictEqual(ed.__pasteCount, 1);
  assert.strictEqual(ed.__lastPasteText, '');
});

test('writeInputValue：元素为空时安全返回假', () => {
  const A = loadBridge();
  assert.strictEqual(A.writeInputValue(null, 'x'), false);
});

test('writeRichEditor：paste 抛异常时返回假且不穿透', () => {
  global.DataTransfer = FakeDataTransfer;
  // 构造一个派发即抛的编辑器，模拟受限环境
  global.ClipboardEvent = function () { throw new Error('ClipboardEvent blocked'); };
  const A = loadBridge();
  const ed = fakeEditable();
  assert.strictEqual(A.writeRichEditor(ed, 'x'), false);
});

test('clearRichEditor：本就为空时不扰动页面', () => {
  const A = loadBridge();
  let execCount = 0;
  global.document.execCommand = () => { execCount += 1; return true; };
  const ed = fakeEditable();
  ed.textContent = '';
  A.clearRichEditor(ed);
  assert.strictEqual(execCount, 0);
});

test('clearRichEditor：有内容时执行全选删除', () => {
  const A = loadBridge();
  const calls = [];
  global.document.execCommand = (cmd) => { calls.push(cmd); return true; };
  const ed = fakeEditable();
  ed.textContent = '残留文本';
  A.clearRichEditor(ed);
  assert.deepEqual(calls, ['selectAll', 'delete']);
});
