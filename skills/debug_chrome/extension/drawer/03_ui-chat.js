// 聊天视图渲染
(function () {
  const D = window.AIDrawer;
  const { h } = D;

  // ctx 需包含：connected, messages, toolCards, msgList, draft, selecting,
  //            selectedElements, clearHistory, close, toggleSelect,
  //            clearElements, removeElement, send, view
  D.createChatRenderer = function (ctx) {
    /**
     * 从工具结果里提取截图 dataURL；没有则返回空串。
     * 截图结果结构：{ success, data: { screenshot: 'data:image/...' } }
     * @param {Object} result 工具结果
     * @returns {string} 截图 dataURL
     */
    function extractScreenshot(result) {
      if (!result || !result.data || typeof result.data !== 'object') return '';
      const shot = result.data.screenshot;
      return (typeof shot === 'string' && shot.indexOf('data:image/') === 0) ? shot : '';
    }

    /**
     * 生成结果的展示文本：剥掉截图 base64。
     *
     * 截图结果里那串 base64 动辄数百 KB，直接 JSON.stringify 会糊满界面、
     * 人也读不了。这里把它剔除，改由渲染层用图片展示。
     * @param {Object} result 工具结果
     * @returns {string} 精简后的 JSON 文本
     */
    function resultText(result) {
      if (!result || typeof result !== 'object') return JSON.stringify(result, null, 2);
      if (!extractScreenshot(result)) return JSON.stringify(result, null, 2);
      const copy = Object.assign({}, result, { data: Object.assign({}, result.data) });
      copy.data.screenshot = '（图片见下方）';
      return JSON.stringify(copy, null, 2);
    }

    // 工具调用卡片：展示工具名、参数、状态与结果，与 chat-bridge 的工具卡片同构
    function renderToolCard(card) {
      const kids = [
        h('div', { class: 'card-head' }, [
          h('span', { class: 'toolname' }, '工具调用 · ' + card.tool),
          h('span', { class: ['badge', card.status] }, card.status === 'running' ? '执行中' : (card.status === 'done' ? '完成' : '失败')),
        ]),
        h('pre', { class: 'params-json' }, JSON.stringify(card.params || {}, null, 2)),
      ];
      if (card.result) {
        kids.push(h('pre', { class: 'result' }, resultText(card.result)));
        const shot = extractScreenshot(card.result);
        if (shot) {
          kids.push(h('img', {
            class: 'result-shot',
            src: shot,
            alt: '截图',
            style: 'max-width:100%; height:auto; display:block; margin-top:6px; border:1px solid #ddd; border-radius:4px;'
          }));
        }
      }
      return h('div', { class: 'tool-card', key: 'tc-' + card.id }, kids);
    }

    // 把消息与工具卡片按时间戳合并为一个流，保证时序交叉展示。
    // 每条消息 / 卡片都带 timestamp，统一排序后渲染。
    function buildTimeline() {
      const items = [];
      (ctx.messages.value || []).forEach((msg) => {
        items.push({ kind: 'msg', ts: msg.timestamp || 0, key: 'm-' + msg.id, data: msg });
      });
      (ctx.toolCards.value || []).forEach((card) => {
        items.push({ kind: 'card', ts: card.timestamp || 0, key: 'tc-' + card.id, data: card });
      });
      items.sort((a, b) => a.ts - b.ts);
      return items;
    }

    function renderTimelineItem(item) {
      if (item.kind === 'card') return renderToolCard(item.data);
      const msg = item.data;
      return h('div', { class: ['msg', msg.role], key: item.key }, [
        msg.role === 'user' && msg.status
          ? h('div', { class: ['msg-status', msg.status] }, D.statusLabel(msg.status))
          : null,
        msg.role !== 'system'
          ? h('div', { class: 'meta' }, `${msg.role === 'user' ? '我' : 'AI'} · ${D.formatTime(msg.timestamp)}`)
          : null,

        // 来源页面地址：多页面同时调试时据此区分消息来自哪个页面。
        msg.page_url
          ? h('div', { class: 'meta page-url', title: msg.page_url }, '来自：' + String(msg.page_url))
          : null,

        msg.elements && msg.elements.length
          ? h(
              'div',
              { class: 'element-list' },
              msg.elements.map((el, i) =>
                h('div', { class: 'element-card', key: 'ec-' + i }, [
                  h('div', [h('strong', '选择器：'), ' ' + String(el.selector || '')]),
                  el.selector_confidence === 'low'
                    ? h('div', { class: 'warn' }, '该选择器在当前页面不唯一，定位可能不准')
                    : null,
                  h('div', [h('strong', 'URL：'), ' ' + String(el.page_url || '')]),
                  el.screenshot ? h('img', { src: el.screenshot, alt: '截图' }) : null,
                  el.computed_style && Object.keys(el.computed_style).length
                    ? h('pre', D.styleSummary(el.computed_style))
                    : null,
                  h('details', [
                    h('summary', 'DOM 源码（' + String(el.dom_html || '').length + ' 字符）'),
                    h('pre', { class: 'dom-code' }, String(el.dom_html || ''))
                  ]),
                ])
              )
            )
          : null,

        h('div', { class: 'text' }, String(msg.text || '')),

        // 用户消息提供重新发送：chat-bridge 未收到（如当时后端未就绪）时可补发，
        // 不新增消息条目，也不改动原始已选元素。
        msg.role === 'user'
          ? h('div', { class: 'msg-actions' }, [
              h('button', {
                class: 'icon-btn',
                title: '重新发送到网页 AI',
                onClick: () => ctx.resendMessage(msg),
              }, '↻'),
            ])
          : null,
      ]);
    }

    function renderChat() {
      return h('div', { class: 'drawer' }, [
        h('div', { class: 'header' }, [
          h('span', 'AI Debug'),
          h('div', { class: 'status-bar' }, [
            h('span', { class: ['dot', ctx.connected.value ? 'connected' : 'disconnected'] }),
            h('span', ctx.connected.value ? '已连接' : '未连接'),
            h('button', {
              class: 'icon-btn',
              title: ctx.drawerSide.value === 'left' ? '切换到右侧挂靠' : '切换到左侧挂靠',
              onClick: ctx.switchSide,
            }, ctx.drawerSide.value === 'left' ? '⇥' : '⇤'),
            h('button', { class: 'icon-btn', title: '清空', onClick: ctx.clearHistory }, '⌫'),
            h('button', { class: 'icon-btn', title: '设置', onClick: () => { ctx.view.value = 'settings'; } }, '⚙'),
            h('button', { class: 'icon-btn', title: '关闭', onClick: ctx.close }, '✕'),
          ]),
        ]),

        h(
          'div',
          { class: 'messages', ref: ctx.msgList, onScroll: ctx.onMessagesScroll },
          buildTimeline().map((item) => renderTimelineItem(item))
        ),

        // 未连接只作提示，不拦截输入；发送时由请求本身判断成败，
        // 失败以 toast 告知并保留输入内容，用户可直接重试。
        ctx.connected.value ? null : h('div', { class: 'hint' }, '暂未连上工具服务，发送可能失败，可直接重试。'),

        ctx.toast && ctx.toast.value ? h('div', { class: 'toast-tip' }, String(ctx.toast.value)) : null,

        h('div', { class: 'tools' }, [
          h('button', { class: { active: ctx.selecting.value }, onClick: ctx.toggleSelect, title: '无法选中的元素,可以使用 window.selectAiDebugElement 进行js选择' }, ctx.selecting.value ? '退出选择' : '选择元素'),
          ctx.selectedElements.value.length ? h('button', { onClick: ctx.clearElements }, '清空') : null,
        ]),

        ctx.selectedElements.value.length
          ? h(
              'div',
              { class: 'selected-list' },
              ctx.selectedElements.value.map((el, idx) => {
                // 是否存在「同选择器的更早元素」：有才允许对比去重
                const hasBase = ctx.selectedElements.value.some((x, i) => i < idx && x
                  && x.selector && x.selector === el.selector);
                const isCompacted = !!el.dom_html_full;
                return h('div', { class: 'selected-item', key: 'sel-' + (el.selId || idx) }, [
                  h('div', { class: 'selected-head' }, [
                    h('span', { class: 'selected-title' }, `${idx + 1}. ${String(el.selector || '').slice(0, 60)}`),
                    h('button', { class: 'icon-btn', title: '移除该元素', onClick: () => ctx.removeElement(el.selId, idx) }, '✕'),
                  ]),
                  h('details', { class: 'selected-detail' }, [
                    // 「查看详情」一行集中承载：详情开关、DOM 源码字数、去重 / 还原按钮。
                    // 折叠状态下即可看到字数并直接操作，不必先展开再找。
                    h('summary', { class: 'detail-summary' }, [
                      h('span', { class: 'summary-label' }, '查看详情'),
                      h('span', { class: 'dom-len' }, 'DOM 源码（' + String(el.dom_html || '').length + ' 字符）'),
                      // 去重 / 还原：仅同选择器才有基准可对比；已压缩的显示还原入口。
                      // 按钮在 summary 内，必须阻止默认与冒泡，否则点按钮会连带开合详情。
                      isCompacted
                        ? h('button', {
                            class: 'icon-btn',
                            title: '还原为完整 DOM',
                            onClick: (e) => { e.preventDefault(); e.stopPropagation(); ctx.restoreElement(el.selId); }
                          }, '↺')
                        : (hasBase
                          ? h('button', {
                              class: 'icon-btn',
                              title: '与首个同选择器元素对比去重',
                              onClick: (e) => { e.preventDefault(); e.stopPropagation(); ctx.dedupElement(el.selId); }
                            }, '⧉')
                          : null),
                    ]),
                    h('div', [h('strong', '选择器：'), ' ' + String(el.selector || '')]),
                    el.selector_confidence === 'low'
                      ? h('div', { class: 'warn' }, '该选择器在当前页面不唯一，定位可能不准')
                      : null,
                    h('div', [h('strong', 'URL：'), ' ' + String(el.page_url || '')]),
                    el.screenshot ? h('img', { src: el.screenshot, alt: '截图' }) : null,
                    el.computed_style && Object.keys(el.computed_style).length
                      ? h('pre', D.styleSummary(el.computed_style))
                      : null,
                    h('pre', { class: 'dom-code' }, String(el.dom_html || '')),
                  ]),
                ]);
              })
            )
          : null,

        h('div', { class: 'input-area' }, [
          h('textarea', {
            ref: ctx.inputBox,
            value: ctx.draft.value,
            placeholder: '描述你的调试需求...',
            onInput: (e) => {
              ctx.draft.value = e.target.value;
              ctx.resizeInput();
            },
            onKeydown: (e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                ctx.send();
                ctx.resizeInput();
              }
            },
          }),
          h('button', { onClick: ctx.send, disabled: !ctx.draft.value.trim() }, '发送'),
        ]),
      ]);
    }

    return { renderChat };
  };
})();
