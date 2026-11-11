// 模块：extend/lib/tool-schema-adapter.js
// 用途：把标准 JSON Schema 参数声明还原为旧扁平参数项，供设置页与提示词复用。
// 对外接口：window.AIMirrorToolSchema = { toFlatParams }
// 依赖：无（纯数据转换，不持有界面状态，与 dom-utils.js 同属 lib 层）。
//
// 背景：阶段 1b 后端参数声明已迁为标准 JSON Schema，字段为
// { type: 'object', properties: {...}, required: [...] }；前端三处仍按
// 旧扁平数组 [ { name, type, required, description } ] 读取，对对象调 .map
// 会渲染中断。本模块做单向还原，不回写后端声明。
(function (global) {
  'use strict';

  /** 取属性展示类型；anyOf 取首支，无 type 时回退 string。 */
  function displayType(prop) {
    // 联合类型仅用于展示：取第一支的 type，与 split-mirror 决策 8 一致。
    if (Array.isArray(prop.anyOf) && prop.anyOf.length) {
      return (prop.anyOf[0] && prop.anyOf[0].type) || 'string';
    }
    return prop.type || 'string';
  }

  /**
   * 标准 schema（或旧扁平数组）→ 旧扁平参数项数组。
   * @param {Object|Array} schema 工具参数声明
   * @returns {Array<{name,type,required,description}>} 扁平参数项
   */
  function toFlatParams(schema) {
    // 旧数组原样返回副本：兼容旧 tool.json 与编辑区里的历史数据。
    if (Array.isArray(schema)) return schema.slice();
    // 非对象或缺失 properties 按空参数表处理，不让渲染抛异常。
    if (!schema || typeof schema !== 'object') return [];
    const props = schema.properties || {};
    const required = Array.isArray(schema.required) ? schema.required : [];
    const requiredSet = new Set(required);
    // properties 的键即参数名，顺序按声明顺序保留。
    return Object.keys(props).map((name) => {
      const p = props[name] || {};
      return {
        name: name,
        type: displayType(p),
        required: requiredSet.has(name),
        description: p.description || '',
      };
    });
  }

  const api = { toFlatParams: toFlatParams };
  // 浏览器侧挂全局，供 dialog 各 parts 以 <script> 方式直接取用。
  global.AIMirrorToolSchema = api;
  // Node 测试侧同时导出，便于 node --test 直接 require。
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
