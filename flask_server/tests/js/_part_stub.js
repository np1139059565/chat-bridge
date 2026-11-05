/* ============================================================
 * 分片测试的公共全局桩
 *
 * 为什么独立成文件：
 *   多个测试文件都要先把 window.AIMirrorDialog 立起来，再 require 被测分片。
 *   这段桩代码逐字相同，各写一份既触发重复代码检测，改一处又容易漏改另一处。
 *   抽到此处后，桩的定义只有一份。
 *
 * 命名约定（同 _dialog_fixture.js）：
 *   文件名以 _ 开头、不以 .test.js 结尾，因此不会被 node --test
 *   当作测试文件执行，也不参与覆盖率阈值校验。
 * ============================================================ */

/**
 * 立起最小全局桩，返回挂方法用的 dialog 命名空间。
 *
 * 桩只提供分片脚本启动阶段会碰到的成员；测试若需要更完整的实现
 * （例如真实的消息指纹），应在调用本函数后再 require 对应真实模块，
 * 由真实模块覆盖这里的哑实现。
 *
 * @returns {Object} dialog 命名空间（含 methods 容器）
 */
function installStub() {
  const dialog = { methods: {}, log: () => {} };
  global.window = {
    AIMirrorDialog: dialog,
    // toArray：块可能以对象或数组两种形态存，统一成数组
    AIMirrorDomUtils: { toArray: (v) => (Array.isArray(v) ? v : []) }
  };
  return dialog;
}

module.exports = { installStub };
