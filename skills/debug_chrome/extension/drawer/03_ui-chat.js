// 聊天视图渲染
(function () {
  const D = window.AIDrawer;
  const { h } = D;

  // ctx 需包含：open, connected, messages, toolCards, msgList, draft, selecting,
  //            selectedElements, clearHistory, toggle, toggleSelect,
  //            clearElements, removeElement, send, view
  D.createChatRenderer = function (ctx) {
    // 工具调用卡片：展示工具名、参数、状态与结果，与 chat-bridge 的工具卡片同构
    function renderToolCard(card) {
      const kids = [
        h('div', { class: 'card-head' }, [
          h('span', { class: 'toolname' }, '工具调用 · ' + card.tool),
          h('span', { class: ['badge', card.status] }, card.status === 'running' ? '执行中' : (card.status === 'done' ? '完成' : '失败')),
        ]),
        h('pre', { class: 'params-json' }, JSON.stringify(card.params || {}, null, 2)),
      ];
      if (card.result) kids.push(h('pre', { class: 'result' }, JSON.stringify(card.result, null, 2)));
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
                  h('details', [h('summary', 'DOM 源码'), h('pre', { class: 'dom-code' }, String(el.dom_html || ''))]),
                ])
              )
            )
          : null,

        h('div', { class: 'text' }, String(msg.text || '')),
      ]);
    }

    function renderChat() {
      return h('div', { class: ['drawer', { open: ctx.open.value }] }, [
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
            h('button', { class: 'icon-btn', onClick: ctx.clearHistory }, '清空'),
            h('button', { class: 'icon-btn', onClick: () => { ctx.view.value = 'settings'; } }, '设置'),
            h('button', { class: 'icon-btn', onClick: ctx.toggle }, '×'),
          ]),
        ]),

        h(
          'div',
          { class: 'messages', ref: ctx.msgList },
          buildTimeline().map((item) => renderTimelineItem(item))
        ),

        ctx.connected.value ? null : h('div', { class: 'hint' }, '后端服务未运行，请在 AI 客户端执行调试 Skill 启动。'),

        ctx.toast && ctx.toast.value ? h('div', { class: 'toast-tip' }, String(ctx.toast.value)) : null,

        h('div', { class: 'tools' }, [
          h('button', { class: { active: ctx.selecting.value }, onClick: ctx.toggleSelect }, ctx.selecting.value ? '退出选择' : '选择元素'),
          ctx.selectedElements.value.length ? h('button', { onClick: ctx.clearElements }, '清空已选') : null,
        ]),

        ctx.selectedElements.value.length
          ? h(
              'div',
              { class: 'selected-list' },
              ctx.selectedElements.value.map((el, idx) =>
                h('div', { class: 'selected-item', key: 'sel-' + (el.selId || idx) }, [
                  h('span', `${idx + 1}. ${String(el.selector || '').slice(0, 60)}`),
                  h('button', { class: 'icon-btn', onClick: () => ctx.removeElement(el.selId, idx) }, '移除'),
                ])
              )
            )
          : null,

        h('div', { class: 'input-area' }, [
          h('textarea', {
            value: ctx.draft.value,
            disabled: !ctx.connected.value,
            placeholder: '描述你的调试需求...',
            onInput: (e) => {
              ctx.draft.value = e.target.value;
            },
            onKeydown: (e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                ctx.send();
              }
            },
          }),
          h('button', { onClick: ctx.send, disabled: !ctx.connected.value || !ctx.draft.value.trim() }, '发送'),
        ]),
      ]);
    }

    return { renderChat };
  };
})();
