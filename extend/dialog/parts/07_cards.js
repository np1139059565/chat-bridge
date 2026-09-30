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
   * 从工具结果里提取截图 dataURL。
   * 截图工具（get_page_snapshot）的结果结构：
   *   { success:true, data:{ screenshot:'data:image/...', saved:{...} } }
   * @param {Object} result 工具结果
   * @returns {string} 截图 dataURL；没有则返回空串
   */
  D.extractScreenshot = function (result) {
    if (!result || !result.data || typeof result.data !== 'object') return '';
    const shot = result.data.screenshot;
    return (typeof shot === 'string' && shot.indexOf('data:image/') === 0) ? shot : '';
  };

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
   * @param {Object} [opts] 可选配置
   * @param {boolean} [opts.readonly] 只读模式：不渲染任何交互控件，
   *   堆栈直接展开显示。用于「会话记录」这类只作留档展示的场景。
   * @returns {VNode} 卡片节点
   */
  D.renderCodeCard = function (ctx, block, opts) {
    const readonly = !!(opts && opts.readonly);
    const card = ctx.cardMap[block.id];
    const isTool = !!(card && card.isTool);
    // 是否正处于「回传倒计时」：是则把倒计时显示在「复制结果」按钮上，
    // 且该按钮此时点击 = 跳过等待、立即回传。
    const sending = isTool && !readonly && card.phase === 'send' && card.countdown > 0;
    const kids = [
      h('div', { class: 'code-head' }, [
        isTool
          ? h('span', { class: 'toolname' }, '工具调用 · ' + card.tool)
          : h('span', { class: 'lang' }, String(block.lang || 'code').toUpperCase()),
        // 卡片门牌号：紧跟工具名显示该卡片的 id，点击即复制。
        // 展开卡片后一眼可见，便于排查卡片重复 / 定位到具体哪张卡。
        (isTool && card.id)
          ? h('span', {
              class: 'card-id',
              title: '卡片 id：' + card.id + '（点击复制）',
              onClick: () => ctx.copy(card.id)
            }, card.id)
          : null,
        h('span', { class: 'head-controls' }, [
          // 跳过的卡片状态独立显示：status 仍为 pending，直接用 statusText 会误显示「待执行」
          isTool
            ? h('span', { class: 'badge ' + (card.skipped ? 'skipped' : card.status) },
              card.skipped ? '已跳过' : ctx.statusText(card.status))
            : null,
          // 自动流程的倒计时统一写在按钮文案里（执行按钮 / 复制结果按钮），
          // 卡片头部不再单独显示一份，避免同一件事重复呈现。
          // 带问题的卡片同样提供「自动」开关：它仍会进入自动执行候选，隐藏开关只会造成界面与实际行为不一致。
          (isTool && !readonly) ? D.renderAutoSwitch(ctx) : null
        ])
      ])
    ];
    if (isTool) {
      // 质量问题不再单独用警示横幅显示：它已作为正常结果返回（见 executeCard），
      // 由下方结果区统一呈现，避免同一内容重复两处。
      kids.push(h('pre', { class: 'params-json' }, JSON.stringify(card.parameters, null, 2)));
      // 操作行仅在非只读模式渲染
      if (!readonly) {
        kids.push(h('div', { class: 'row' }, [
          h('button', {
            onClick: () => ctx.onExecuteClick(card),
            disabled: card.status === 'running'
          }, ctx.execButtonLabel(card)),
          // 跳过：取消该卡片的倒计时与自动回传，用户可自行决定不执行
          (!card.skipped && !card.executed) ? h('button', { class: 'secondary', onClick: () => ctx.skipCard(card) }, '跳过') : null,
          card.skipped ? h('span', { class: 'hint' }, '已跳过') : null,
          // 「复制结果」按钮：有结果时显示；自动回传倒计时中也显示，
          // 并在按钮上显示剩余秒数。倒计时期间点击 = 跳过等待立即回传。
          ((card.result != null || card.error) || sending)
            ? h('button', {
              onClick: () => ctx.onResultClick(card)
            }, '复制结果' + (sending ? card.countdown + 's' : ''))
            : null
        ]));
      } else if (card.skipped) {
        // 只读模式没有按钮行，跳过状态改为独立提示，避免状态信息丢失
        kids.push(h('div', { class: 'hint' }, '已跳过'));
      }
      if (card.status === 'done') {
        // 结果是截图时，渲染等比缩放的图片；否则仍以文本展示结果。
        const shot = D.extractScreenshot(card.result);
        if (shot) {
          kids.push(h('img', {
            class: 'result-shot',
            src: shot,
            alt: '页面截图',
            style: 'max-width:100%; height:auto; display:block; margin-top:6px; border:1px solid #ddd; border-radius:4px;'
          }));
        } else {
          kids.push(h('pre', { class: 'result' }, ctx.fmt(card.result)));
        }
      }
      if (card.status === 'error') {
        kids.push(h('pre', { class: 'error' }, card.error || ctx.fmt(card.result)));
        if (card.origin) {
          kids.push(h('div', { class: 'origin-line' },
            '错误分类：' + card.origin +
            (card.origin === 'tool_internal'
              ? ' — 本地工具代码缺陷，改参数无效，需检查工具实现'
              : '')));
        }
        if (card.stack) {
          // 只读模式直接把堆栈展开：没有展开按钮，若仍按折叠逻辑渲染，
          // 堆栈内容将永远无法看到，而它正是留档时最需要的信息。
          if (readonly) {
            kids.push(h('pre', { class: 'stack' }, card.stack));
          } else {
            const open = !!ctx.stackOpen[card.id];
            kids.push(h('div', { class: 'row' }, [
              h('button', { onClick: () => { ctx.stackOpen[card.id] = !open; } },
                open ? '收起堆栈' : '查看完整堆栈')
            ]));
            if (open) kids.push(h('pre', { class: 'stack' }, card.stack));
          }
        }
      }
    } else {
      kids.push(h('pre', { class: 'code-body' }, block.code));
      if (!readonly) {
        kids.push(h('div', { class: 'row' }, [
          h('button', { onClick: () => ctx.copy(block.code) }, '复制代码')
        ]));
      }
    }
    return h('div', { class: 'code-card', key: block.id }, kids);
  };

  /**
   * 把一条 external-call 用户消息还原为外部卡片（镜像区展示用）。
   * 外部卡片发送到网页后以 user 消息存在，这里按卡片外观重新呈现，
   * 并加 external-call 标记类，供配色区分。
   * @param {Object} ctx Vue 实例
   * @param {Object} node 消息节点
   * @param {Object} parsed parseExternalCall 的返回值
   * @returns {VNode} 卡片节点
   */
  D.renderExternalCallMessage = function (ctx, node, parsed) {
    const key = 'ext-' + (parsed.nonce || window.AIMirrorDomUtils.messageFingerprint(node));
    const kids = [
      h('div', { class: 'code-head' }, [
        h('span', { class: 'toolname' }, '用户'),
        h('span', { class: 'head-controls' }, [
          h('span', { class: 'badge done' }, '已发送')
        ])
      ]),
      h('pre', { class: 'params-json' }, parsed.request || '')
    ];
    return h('div', { class: 'code-card external-call-card', key: key }, kids);
  };

  /**
   * 按块类型渲染，保留原网页的内容分类（标题 / 段落 / 列表 / 引用 / 表格 / 思考 / 代码）。
   * @param {Object} ctx Vue 实例
   * @param {Object} block 块对象
   * @param {number} j 块在消息内的下标
   * @param {string} mKey 消息键
   * @param {Object} [opts] 可选配置（透传给卡片渲染，如只读模式）
   * @returns {VNode} 块节点
   */
  D.renderBlock = function (ctx, block, j, mKey, opts) {
    const k = mKey + '-' + j;
    if (block.type === 'heading') return h('div', { class: 'mb-h', key: k }, block.text);
    if (block.type === 'paragraph') return h('p', { class: 'mb-p', key: k }, block.text);
    if (block.type === 'list') {
      // items 归一化：网页推送或旧存档可能把它序列化成非数组，直接 map 会抛错。
      const items = D.toArray(block.items);
      return block.ordered
        ? h('ol', { class: 'mb-list', key: k }, items.map((t, n) => h('li', { key: n }, t)))
        : h('ul', { class: 'mb-list', key: k }, items.map((t, n) => h('li', { key: n }, t)));
    }
    if (block.type === 'quote') return h('blockquote', { class: 'mb-quote', key: k }, block.text);
    if (block.type === 'table') {
      // rows 与每行单元格都归一化：非数组会被序列化成对象 / 字符串，
      // 直接 map 会抛错；逐行再归一化，避免行内是对象时二次崩溃。
      const rows = D.toArray(block.rows);
      return h('table', { class: 'mb-table', key: k }, [
        h('tbody', rows.map((row, r) => h('tr', { key: r },
          D.toArray(row).map((cell, c) => h(r === 0 ? 'th' : 'td', { key: c }, cell))
        )))
      ]);
    }
    if (block.type === 'thinking') {
      // 两种模式统一支持点击折叠。默认态不同：
      //  - 只读模式（会话记录留档）默认展开：直接看到内容，点击可收起；
      //  - 非只读模式（镜像区）默认折叠：节省纵向空间，点击可展开。
      // 折叠状态用同一个 thinkOpen 存储；k 由 mKey + 下标构成，两处互不冲突。
      const readonly = !!(opts && opts.readonly);
      const open = (ctx.thinkOpen[k] === undefined) ? readonly : !!ctx.thinkOpen[k];
      return h('div', { class: 'mb-think', key: k }, [
        h('div', { class: 'mb-think-head', onClick: () => { ctx.thinkOpen[k] = !open; } },
          (open ? '▾' : '▸') + ' 思考过程'),
        open ? h('div', { class: 'mb-think-body' }, block.text) : null
      ]);
    }
    if (block.type === 'code') return D.renderCodeCard(ctx, block, opts);
    return h('p', { class: 'mb-p', key: k }, block.text || '');
  };

  /**
   * 取消息的首行纯文本，作为折叠态下的预览摘要。
   * @param {Object} m 消息对象
   * @returns {string} 预览文本
   */
  D.firstLine = function (m) {
    const blocks = D.toArray(m.blocks);
    for (let i = 0; i < blocks.length; i++) {
      const b = blocks[i];
      // items 归一化后再 join：非数组值直接 join 会抛 TypeError。
      const t = b && (b.text || b.code || (b.items && D.toArray(b.items).join(' ')) || '');
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
      // h('div', { class: 'avatar' }, avatar),//无需头像,占用大量宽度
      h('div', { class: 'bubble' }, [
        h('div', { class: 'user-head', onClick: () => { store[mKey] = !open; } }, [
          h('span', { class: 'caret' }, open ? '▾' : '▸'),
          h('span', { class: 'who-inline' }, m.name || 'AI'),
          open ? null : h('span', { class: 'user-preview' }, D.firstLine(m))
        ]),
        open ? h('div', { class: 'blocks' }, D.toArray(m.blocks).map((b, j) => D.renderBlock(ctx, b, j, mKey))) : null
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
    // external-call 信封：这不是普通用户消息，而是外部卡片的本体，
    // 在镜像区还原为卡片外观呈现，并加标记色，便于与普通消息区分。
    if (isUser) {
      const ext = ctx.parseExternalCall ? ctx.parseExternalCall(m) : null;
      if (ext) return D.renderExternalCallMessage(ctx, m, ext);
    }
    // 用户消息：默认折叠，点标题行展开 / 收起
    if (isUser) return D.renderCollapsible(ctx, m, mKey, 'user', '我', ctx.userOpen);
    // 消息在消息树中的 key（父id-子id）：显示在标题行上，点击可跳到
    // 「会话记录」中对应条目并自动展开，便于从镜像直接定位到该条记录。
    const mid = window.AIMirrorDomUtils.messageFingerprint(m);
    const treeKey = ctx.msgTreeKeyOf(mid);
    return h('div', { class: 'msg assistant', key: mKey }, [
      h('div', { class: 'bubble' }, [
        h('div', { class: 'who' }, [
          m.name || 'AI',
          treeKey
            ? h('span', {
              class: 'msg-pid',
              title: '点击跳转到「会话记录」中的该条消息',
              onClick: () => ctx.jumpToSessionEntry(mid)
            }, treeKey)
            : null
        ]),
        h('div', { class: 'blocks' }, D.toArray(m.blocks).map((b, j) => D.renderBlock(ctx, b, j, mKey)))
      ])
    ]);
  };
})();
