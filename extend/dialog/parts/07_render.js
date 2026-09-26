// 模块：extend/dialog/parts/07_render.js
// 用途：组件渲染函数。仅做整体装配：设置面板 + 消息镜像 + 头部。
//       具体卡片 / 设置面板渲染见 07_cards.js、08_settings.js。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、
//       parts/07_cards.js、parts/08_settings.js、Vue 全局构建
//
// 说明：Manifest V3 扩展页 CSP 禁止 unsafe-eval，因此不能用 template 字符串，
// 这里统一使用渲染函数 h()，无需运行期编译器。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const h = Vue.h;

  /** 组件渲染函数：组装设置面板与主界面。 */
  D.render = function () {
    const ctx = this;

    // 顺序由消息树结构与锚点决定：消息按可见区 key 顺序，外部卡片按锚点插到
    // 对应消息之后。锚点不在可见列表里的已处理卡片不显示（其内容已滚出视野）；
    // 未处理的卡片放末尾，允许堆在底部等用户决定。
    // 镜像列表：优先用可见区时序；可见区为空（切片未入树）时，展示该切片内容。
    const orphanMsgs = (ctx.curConv.orphanSlice || []);
    const timeline = D.buildTimeline(ctx.curConv, ctx.curConv.visibleKeys || [], { orphanMode: 'skip-handled' });
    const listItems = (timeline && timeline.length)
      ? timeline
      : orphanMsgs.map(function (m, i) { return { kind: 'message', key: 'orphan-' + i, node: m }; });
    // 镜像按「最新在前」倒序渲染，与网页对话一致
    const mirrorItems = listItems.slice().reverse().map((it, idx) => {
      if (it.kind === 'message') return D.renderMessage(ctx, it.node, idx, idx);
      return D.renderExternalCard(ctx, it.card);
    });

    // 主界面只保留网页对话镜像（外部卡片与工具卡片一并呈现）
    const mirrorBlock = h('section', { class: 'card' }, [
      // 头部加 card-head-sticky：滚动时吸附在滚动区顶部，数量与按钮不被内容淹没
      h('div', { class: 'card-head card-head-sticky' }, [
        h('span', '网页对话镜像（' + ctx.messages.length + '）'),
        h('span', { class: 'head-actions' }, [
          h('button', { onClick: () => ctx.reparse() }, '重新解析'),
          h('button', { onClick: () => ctx.copyConversationJson() }, '复制')
        ])
      ]),
      ctx.curConv.title ? h('div', { class: 'conv-title' }, '当前会话：' + ctx.curConv.title) : null,
      mirrorItems.length
        ? h('div', { class: 'mirror' }, mirrorItems)
        : h('div', { class: 'empty' }, '（等待网页对话内容…）')
    ]);

    const body = h('div', { class: 'm-body' }, [mirrorBlock]);

    return h('div', { class: 'mirror-app' }, [
      h('header', { class: 'm-header' }, [
        h('div', { class: 'title' }, [
          'AI 工具调用镜像',
          ctx.siteKey ? h('span', { class: 'site-badge' }, ctx.siteKey) : null
        ]),
        h('div', { class: 'actions' }, [
          h('button', {
            title: ctx.panelSide === 'left' ? '切换到右侧挂靠' : '切换到左侧挂靠',
            onClick: () => ctx.switchPanelSide()
          }, ctx.panelSide === 'left' ? '⇥' : '⇤'),
          h('button', {
            title: '设置',
            onClick: () => {
              ctx.settingsOpen = !ctx.settingsOpen;
              // 打开设置页时清空条目的勾选态与展开态：条目 key 含消息下标，
              // 消息被重解析后下标会变化，残留状态会错位到别的条目上。
              if (ctx.settingsOpen) {
                Object.keys(ctx.entryChecked).forEach((k) => { delete ctx.entryChecked[k]; });
                Object.keys(ctx.entryOpen).forEach((k) => { delete ctx.entryOpen[k]; });
                // 打开设置页时扫描存储里的全部会话，保证左侧会话列表显示完整，
                // 而不是只有当前已读入内存的这一个。
                ctx.scanConversations();
              }
            }
          }, '⚙'),
          h('button', { title: '关闭', onClick: () => ctx.closePanel() }, '✕')
        ])
      ]),
      D.renderSettings(ctx),
      body,
      ctx.toastMsg ? h('div', { class: 'toast' }, ctx.toastMsg) : null
    ]);
  };
})();
