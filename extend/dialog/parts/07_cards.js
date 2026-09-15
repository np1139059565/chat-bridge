// 模块：extend/dialog/parts/07_cards.js
// 用途：对话镜像内的卡片与消息渲染：代码卡片、块渲染、消息条目。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、Vue 全局构建
//
// 说明：这些渲染函数原先定义在 D.render 内部，依赖 Vue 实例上下文（this）。
// 拆分后统一改为 D.renderXxx(ctx, ...) 形式，ctx 即 Vue 实例，语义与原实现一致。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const h = Vue.h;

  /**
   * 渲染「自动」开关：工具卡片与外部卡片共用同一视觉与行为。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 开关节点
   */
  D.renderAutoSwitch = function (ctx) {
    return h('label', { class: 'auto-send' }, [
      h('input', {
        type: 'checkbox',
        checked: ctx.autoSendEnabled,
        onChange: (e) => ctx.setAutoSendEnabled(e.target.checked)
      }),
      '自动'
    ]);
  };

  /**
   * 渲染一个代码块为卡片：工具调用卡片可执行，普通代码卡片提供复制。
   * @param {Object} ctx Vue 实例
   * @param {Object} block 代码块
   * @returns {VNode} 卡片节点
   */
  D.renderCodeCard = function (ctx, block) {
    const card = ctx.cardMap[block.id];
    const isTool = !!(card && card.isTool);
    const kids = [
      h('div', { class: 'code-head' }, [
        isTool
          ? h('span', { class: 'toolname' }, '工具调用 · ' + card.tool)
          : h('span', { class: 'lang' }, String(block.lang || 'code').toUpperCase()),
        h('span', { class: 'head-controls' }, [
          isTool ? h('span', { class: 'badge ' + card.status }, ctx.statusText(card.status)) : null,
          isTool ? D.renderAutoSwitch(ctx) : null,
          (isTool && card.countdown > 0) ? h('span', { class: 'countdown' }, (card.phase === 'send' ? '回传 ' : '执行 ') + card.countdown + 's') : null
        ])
      ])
    ];
    if (isTool) {
      kids.push(h('pre', { class: 'params-json' }, JSON.stringify(card.parameters, null, 2)));
      kids.push(h('div', { class: 'row' }, [
        h('button', {
          onClick: () => ctx.onExecuteClick(card),
          disabled: card.status === 'running'
        }, ctx.execButtonLabel(card)),
        // 跳过：取消该卡片的倒计时与自动回传，用户可自行决定不执行
        (!card.skipped && !card.executed) ? h('button', { class: 'secondary', onClick: () => ctx.skipCard(card) }, '跳过') : null,
        card.skipped ? h('span', { class: 'hint' }, '已跳过') : null,
        (card.result != null || card.error) ? h('button', { onClick: () => ctx.copy(ctx.resultText(card)) }, '复制结果') : null
      ]));
      if (card.status === 'done') kids.push(h('pre', { class: 'result' }, ctx.fmt(card.result)));
      if (card.status === 'error') {
        kids.push(h('pre', { class: 'error' }, card.error || ctx.fmt(card.result)));
        if (card.origin) {
          kids.push(h('div', { class: 'origin-line' },
            '错误分类：' + card.origin +
            (card.origin === 'tool_internal'
              ? ' — 本地工具代码缺陷，请用 hot_reload_fix 修代码，改参数无效'
              : '')));
        }
        if (card.stack) {
          const open = !!ctx.stackOpen[card.id];
          kids.push(h('div', { class: 'row' }, [
            h('button', { onClick: () => { ctx.stackOpen[card.id] = !open; } },
              open ? '收起堆栈' : '查看完整堆栈')
          ]));
          if (open) kids.push(h('pre', { class: 'stack' }, card.stack));
        }
      }
    } else {
      kids.push(h('pre', { class: 'code-body' }, block.code));
      kids.push(h('div', { class: 'row' }, [
        h('button', { onClick: () => ctx.copy(block.code) }, '复制代码')
      ]));
    }
    return h('div', { class: 'code-card', key: block.id }, kids);
  };

  /**
   * 按块类型渲染，保留原网页的内容分类（标题 / 段落 / 列表 / 引用 / 表格 / 思考 / 代码）。
   * @param {Object} ctx Vue 实例
   * @param {Object} block 块对象
   * @param {number} j 块在消息内的下标
   * @param {string} mKey 消息键
   * @returns {VNode} 块节点
   */
  D.renderBlock = function (ctx, block, j, mKey) {
    const k = mKey + '-' + j;
    if (block.type === 'heading') return h('div', { class: 'mb-h', key: k }, block.text);
    if (block.type === 'paragraph') return h('p', { class: 'mb-p', key: k }, block.text);
    if (block.type === 'list') {
      return block.ordered
        ? h('ol', { class: 'mb-list', key: k }, block.items.map((t, n) => h('li', { key: n }, t)))
        : h('ul', { class: 'mb-list', key: k }, block.items.map((t, n) => h('li', { key: n }, t)));
    }
    if (block.type === 'quote') return h('blockquote', { class: 'mb-quote', key: k }, block.text);
    if (block.type === 'table') {
      return h('table', { class: 'mb-table', key: k }, [
        h('tbody', block.rows.map((row, r) => h('tr', { key: r },
          row.map((cell, c) => h(r === 0 ? 'th' : 'td', { key: c }, cell))
        )))
      ]);
    }
    if (block.type === 'thinking') {
      const open = !!ctx.thinkOpen[k];
      return h('div', { class: 'mb-think', key: k }, [
        h('div', { class: 'mb-think-head', onClick: () => { ctx.thinkOpen[k] = !open; } },
          (open ? '▾' : '▸') + ' 思考过程'),
        open ? h('div', { class: 'mb-think-body' }, block.text) : null
      ]);
    }
    if (block.type === 'code') return D.renderCodeCard(ctx, block);
    return h('p', { class: 'mb-p', key: k }, block.text || '');
  };

  /**
   * 取消息的首行纯文本，作为折叠态下的预览摘要。
   * @param {Object} m 消息对象
   * @returns {string} 预览文本
   */
  D.firstLine = function (m) {
    const blocks = m.blocks || [];
    for (let i = 0; i < blocks.length; i++) {
      const b = blocks[i];
      const t = b && (b.text || b.code || (b.items && b.items.join(' ')) || '');
      if (t) return String(t).split('\n')[0].slice(0, 120);
    }
    return '';
  };

  /**
   * 折叠行渲染：用户消息默认折叠，点标题行展开 / 收起。
   * @param {Object} ctx Vue 实例
   * @param {Object} m 消息对象
   * @param {string} mKey 消息键
   * @param {string} cls 附加类名
   * @param {string} avatar 头像文字
   * @param {Object} store 折叠状态映射
   * @returns {VNode} 消息节点
   */
  D.renderCollapsible = function (ctx, m, mKey, cls, avatar, store) {
    const open = !!store[mKey];
    return h('div', { class: 'msg ' + cls, key: mKey }, [
      h('div', { class: 'avatar' }, avatar),
      h('div', { class: 'bubble' }, [
        h('div', { class: 'user-head', onClick: () => { store[mKey] = !open; } }, [
          h('span', { class: 'caret' }, open ? '▾' : '▸'),
          h('span', { class: 'who-inline' }, m.name || 'AI'),
          open ? null : h('span', { class: 'user-preview' }, D.firstLine(m))
        ]),
        open ? h('div', { class: 'blocks' }, (m.blocks || []).map((b, j) => D.renderBlock(ctx, b, j, mKey))) : null
      ])
    ]);
  };

  /**
   * 渲染单条消息：用户消息折叠显示，AI 消息直接展开。
   * @param {Object} ctx Vue 实例
   * @param {Object} m 消息对象
   * @param {number} i 索引
   * @param {number} originalIdx 原始下标（用于生成稳定键）
   * @returns {VNode} 消息节点
   */
  D.renderMessage = function (ctx, m, i, originalIdx) {
    const mKey = (m.role || 'msg') + '-' + originalIdx;
    const isUser = m.role === 'user';
    // 用户消息：默认折叠，点标题行展开 / 收起
    if (isUser) return D.renderCollapsible(ctx, m, mKey, 'user', '我', ctx.userOpen);
    return h('div', { class: 'msg assistant', key: mKey }, [
      h('div', { class: 'avatar' }, 'AI'),
      h('div', { class: 'bubble' }, [
        h('div', { class: 'who' }, m.name || 'AI'),
        h('div', { class: 'blocks' }, (m.blocks || []).map((b, j) => D.renderBlock(ctx, b, j, mKey)))
      ])
    ]);
  };
})();
