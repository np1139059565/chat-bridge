// 模块：extend/dialog/parts/07b_params.js
// 用途：工具卡片上「可编辑参数」的渲染与保存逻辑，从 07_cards.js 抽出，
//       使该文件保持在仓库行数上限内。
// 设计：参数始终可编辑。待执行的卡片改完直接执行；已执行的卡片改完点「重新执行」，
//       两者走的都是 card.parameters——即本模块写回的那份。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const h = Vue.h;

  /**
   * 渲染工具卡片的参数编辑区。
   *
   * 两种形态：
   *   只读（会话记录等留档场景）—— 原样展示，不给交互；
   *   可编辑 —— 文本框 + 保存状态提示 + 一键还原。
   * @param {Object} ctx Vue 实例
   * @param {Object} card 工具卡片
   * @param {boolean} readonly 是否只读
   * @returns {VNode} 参数区节点
   */
  D.renderEditableParams = function (ctx, card, readonly) {
    // 兜底：卡片从持久化数据恢复时可能没有 paramsText（早期存档不含该字段），
    // 此时用当前参数序列化一份，避免编辑框显示空白、让用户以为参数丢了。
    if (!card.paramsText) {
      try { card.paramsText = JSON.stringify(card.parameters || {}, null, 2); } catch (e) { card.paramsText = '{}'; }
    }
    // 只读场景：保持原有的等宽展示，不引入任何交互控件
    if (readonly) {
      return h('pre', { class: 'params-json' }, card.paramsText);
    }
    const err = card.paramsError;
    return h('div', { class: 'params-edit' }, [
      h('div', { class: 'params-edit-head' }, [
        h('span', { class: 'hint' }, '参数（可直接修改，执行时用这里的内容）'),
        h('button', {
          class: 'params-reset',
          title: '还原为 AI 最初传的参数',
          onClick: () => ctx.resetCardParams(card),
        }, '还原'),
      ]),
      h('textarea', {
        class: 'params-input' + (err ? ' invalid' : ''),
        spellcheck: false,
        value: card.paramsText,
        // 输入即解析：合法就写回 card.parameters，非法只标红、不污染执行用的那份
        onInput: (ev) => ctx.onCardParamsInput(card, ev.target.value),
      }),
      // 非法 JSON 才提示：合法时不占位，避免每张卡片都挂一行灰字
      err ? h('div', { class: 'params-err' }, err) : null,
    ]);
  };

  /**
   * 处理参数编辑框的输入：解析成功即写回卡片参数。
   *
   * 关键设计：编辑文本与执行参数分开。用户打到一半的非法内容不会被拿去执行，
   * 只在界面上标红提示；一旦解析成功，card.parameters 立刻换成新值，
   * 之后点「执行」或「重新执行」用的都是它，无需额外保存动作。
   * @param {Object} card 工具卡片
   * @param {string} text 输入框文本
   */
  D.methods.onCardParamsInput = function (card, text) {
    card.paramsText = text;
    try {
      const obj = JSON.parse(text);
      // 必须是对象：数组 / 字符串 / 数字都当非法，工具参数只能是键值对
      if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
        throw new Error('参数必须是 JSON 对象');
      }
      card.parameters = obj;
      card.paramsError = '';
    } catch (e) {
      card.paramsError = 'JSON 格式有误：' + (e && e.message ? e.message : e);
    }
    if (this._persist) this._persist();
  };

  /**
   * 一键还原：把参数恢复成 AI 最初传的那份。
   *
   * 还原的是「最初值」而不是「上次成功执行的值」——用户的诉求是「改坏了能退回原样」，
   * 最初值才是稳定参照点。
   * @param {Object} card 工具卡片
   */
  D.methods.resetCardParams = function (card) {
    const orig = card.origParameters || {};
    // 深拷贝再赋值：避免还原后编辑器与原始副本共享同一对象，改一处影响两处
    card.parameters = JSON.parse(JSON.stringify(orig));
    card.paramsText = JSON.stringify(orig, null, 2);
    card.paramsError = '';
    if (this._persist) this._persist();
    this.toast('参数已还原为最初值');
  };
})();
